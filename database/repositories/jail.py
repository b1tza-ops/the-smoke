import random

from database.core.connection import get_connection


BREAKOUT_NERVE_COST = 5
BREAKOUT_WANTED_PENALTY = 3
FAILED_BREAKOUT_JAIL_SECONDS = 60


class JailInteractionError(ValueError):
    pass


def calculate_bail_cost(level, remaining_seconds):
    minutes = max(1, (remaining_seconds + 59) // 60)
    return max(50, level * 75 + minutes * 10)


def calculate_breakout_chance(helper, target_level):
    skill = helper["speed"] + helper["dexterity"]
    return max(
        15,
        min(85, 55 + skill - target_level * 2),
    )


def get_jail_inmates(limit=50):
    """Return players whose jail sentence has not expired."""
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                id,
                user_id,
                name,
                level,
                wanted_level,
                jail_until,
                MAX(
                    0,
                    CAST(
                        (JULIANDAY(jail_until)
                        - JULIANDAY(CURRENT_TIMESTAMP))
                        * 86400 AS INTEGER
                    )
                ) AS remaining_seconds
            FROM players
            WHERE
                jail_until IS NOT NULL
                AND jail_until > CURRENT_TIMESTAMP
            ORDER BY jail_until ASC, name ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        inmates = []
        for row in rows:
            remaining = row[6]
            inmates.append({
                "id": row[0],
                "user_id": row[1],
                "name": row[2],
                "level": row[3],
                "wanted_level": row[4],
                "jail_until": row[5],
                "remaining_seconds": remaining,
                "bail_cost": calculate_bail_cost(
                    row[3],
                    remaining,
                ),
                "reason": "Arrested after a failed crime",
            })
        return inmates
    finally:
        connection.close()


def bail_out_inmate(helper_user_id, target_player_id):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        helper, target = _load_participants(
            connection,
            helper_user_id,
            target_player_id,
        )
        _validate_interaction(helper, target)

        remaining = _remaining_seconds(
            connection,
            target["jail_until"],
        )
        cost = calculate_bail_cost(
            target["level"],
            remaining,
        )
        if helper["money"] < cost:
            raise JailInteractionError(
                f"You need £{cost:,} to pay this bail."
            )

        connection.execute(
            """
            UPDATE players
            SET money = money - ?
            WHERE id = ?
            """,
            (cost, helper["id"]),
        )
        released = connection.execute(
            """
            UPDATE players
            SET jail_until = NULL
            WHERE
                id = ?
                AND jail_until > CURRENT_TIMESTAMP
            """,
            (target["id"],),
        )
        if released.rowcount != 1:
            raise JailInteractionError(
                "This player has already been released."
            )

        connection.commit()
        return {
            "success": True,
            "action": "bail",
            "cost": cost,
            "target_name": target["name"],
            "target_user_id": target["user_id"],
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def attempt_jail_break(
    helper_user_id,
    target_player_id,
    rng=None,
):
    if rng is None:
        rng = random

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        helper, target = _load_participants(
            connection,
            helper_user_id,
            target_player_id,
        )
        _validate_interaction(helper, target)

        if helper["nerve"] < BREAKOUT_NERVE_COST:
            raise JailInteractionError(
                f"You need {BREAKOUT_NERVE_COST} nerve "
                "for a breakout attempt."
            )

        chance = calculate_breakout_chance(
            helper,
            target["level"],
        )
        roll = rng.randint(1, 100)
        connection.execute(
            """
            UPDATE players
            SET nerve = nerve - ?
            WHERE id = ?
            """,
            (BREAKOUT_NERVE_COST, helper["id"]),
        )

        if roll <= chance:
            released = connection.execute(
                """
                UPDATE players
                SET jail_until = NULL
                WHERE
                    id = ?
                    AND jail_until > CURRENT_TIMESTAMP
                """,
                (target["id"],),
            )
            if released.rowcount != 1:
                raise JailInteractionError(
                    "This player has already been released."
                )
            consequence = None
            success = True
        else:
            caught = roll > 90
            connection.execute(
                """
                UPDATE players
                SET
                    wanted_level = MIN(
                        100,
                        wanted_level + ?
                    ),
                    jail_until = CASE
                        WHEN ? THEN DATETIME(
                            CURRENT_TIMESTAMP,
                            ?
                        )
                        ELSE jail_until
                    END
                WHERE id = ?
                """,
                (
                    BREAKOUT_WANTED_PENALTY,
                    caught,
                    (
                        f"+{FAILED_BREAKOUT_JAIL_SECONDS} "
                        "seconds"
                    ),
                    helper["id"],
                ),
            )
            consequence = (
                "caught"
                if caught
                else "wanted"
            )
            success = False

        connection.commit()
        return {
            "success": success,
            "action": "breakout",
            "chance": chance,
            "roll": roll,
            "nerve_spent": BREAKOUT_NERVE_COST,
            "consequence": consequence,
            "target_name": target["name"],
            "target_user_id": target["user_id"],
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _load_participants(
    connection,
    helper_user_id,
    target_player_id,
):
    query = """
        SELECT
            id,
            user_id,
            name,
            level,
            money,
            nerve,
            speed,
            dexterity,
            jail_until,
            hospital_until,
            travel_destination
        FROM players
        WHERE {field} = ?
    """
    helper_row = connection.execute(
        query.format(field="user_id"),
        (helper_user_id,),
    ).fetchone()
    target_row = connection.execute(
        query.format(field="id"),
        (target_player_id,),
    ).fetchone()

    if helper_row is None or target_row is None:
        raise JailInteractionError(
            "The selected player could not be found."
        )

    fields = (
        "id",
        "user_id",
        "name",
        "level",
        "money",
        "nerve",
        "speed",
        "dexterity",
        "jail_until",
        "hospital_until",
        "travel_destination",
    )
    return (
        dict(zip(fields, helper_row)),
        dict(zip(fields, target_row)),
    )


def _validate_interaction(helper, target):
    if helper["id"] == target["id"]:
        raise JailInteractionError(
            "You cannot release yourself."
        )
    if (
        target["jail_until"] is None
        or _timestamp_expired(target["jail_until"])
    ):
        raise JailInteractionError(
            "This player is no longer in jail."
        )
    if (
        helper["jail_until"] is not None
        and not _timestamp_expired(helper["jail_until"])
    ):
        raise JailInteractionError(
            "You cannot help someone while in jail."
        )
    if (
        helper["hospital_until"] is not None
        and not _timestamp_expired(
            helper["hospital_until"]
        )
    ):
        raise JailInteractionError(
            "You cannot help someone from hospital."
        )
    if helper["travel_destination"] is not None:
        raise JailInteractionError(
            "You cannot help someone while travelling."
        )


def _timestamp_expired(timestamp):
    connection = get_connection()
    try:
        return connection.execute(
            "SELECT ? <= CURRENT_TIMESTAMP",
            (timestamp,),
        ).fetchone()[0] == 1
    finally:
        connection.close()


def _remaining_seconds(connection, timestamp):
    return max(
        0,
        connection.execute(
            """
            SELECT CAST(
                (JULIANDAY(?) - JULIANDAY(CURRENT_TIMESTAMP))
                * 86400 AS INTEGER
            )
            """,
            (timestamp,),
        ).fetchone()[0],
    )
