import random
import sqlite3
from datetime import datetime, timezone

from database.core.connection import get_connection
from game.admin.mischief import AdminActionError, get_prank
from game.player.status import MAX_WANTED_LEVEL
from game.world.districts import DISTRICTS, get_district


def get_admin_player_overview(search="", status="all"):
    search = str(search or "").strip()
    status = status if status in {
        "all", "online", "unverified", "restricted",
    } else "all"
    clauses = []
    parameters = []

    if search:
        term = f"%{search}%"
        clauses.append(
            "(users.username LIKE ? OR users.email LIKE ? "
            "OR players.name LIKE ?)"
        )
        parameters.extend((term, term, term))
    if status == "online":
        clauses.append("players.last_seen >= DATETIME('now', '-5 minutes')")
    elif status == "unverified":
        clauses.append("users.email_verified = 0")
    elif status == "restricted":
        clauses.append(
            "(users.account_state != 'active' OR users.suspended_at IS NOT NULL "
            "OR players.jail_until > CURRENT_TIMESTAMP "
            "OR players.hospital_until > CURRENT_TIMESTAMP)"
        )

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    connection = get_connection()

    try:
        return tuple(connection.execute(
            f"""
            SELECT
                users.id,
                users.username,
                users.email,
                users.email_verified,
                users.suspended_at,
                users.created_at,
                players.name,
                players.level,
                players.money,
                players.current_district,
                players.last_seen,
                users.role,
                users.account_state
            FROM users
            LEFT JOIN players
                ON players.user_id = users.id
            {where}
            ORDER BY users.id DESC
            """,
            parameters,
        ).fetchall())
    finally:
        connection.close()


def get_admin_metrics():
    """Small, cheap snapshots for the Operations dashboard."""
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS accounts,
                COALESCE(SUM(users.email_verified = 1), 0) AS verified,
                COALESCE(SUM(
                    players.last_seen >= DATETIME('now', '-5 minutes')
                ), 0) AS online,
                COALESCE(SUM(
                    users.account_state != 'active'
                    OR users.suspended_at IS NOT NULL
                    OR players.jail_until > CURRENT_TIMESTAMP
                    OR players.hospital_until > CURRENT_TIMESTAMP
                ), 0) AS restricted
            FROM users
            LEFT JOIN players ON players.user_id = users.id
            """
        ).fetchone()
        return {
            "accounts": row[0],
            "verified": row[1],
            "online": row[2],
            "restricted": row[3],
        }
    finally:
        connection.close()


def set_user_suspended(user_id, suspended):
    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            UPDATE users
            SET suspended_at = CASE
                WHEN ? THEN CURRENT_TIMESTAMP
                ELSE NULL
            END
            WHERE id = ?
            """,
            (1 if suspended else 0, user_id),
        )
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


def is_user_suspended(user_id):
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT suspended_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        return bool(row and row[0])
    finally:
        connection.close()


def get_admin_player_details(user_id):
    connection = get_connection()
    connection.row_factory = sqlite3.Row

    try:
        account_row = connection.execute(
            """
            SELECT
                users.id AS user_id,
                users.username,
                users.email,
                users.email_verified,
                users.email_verified_at,
                users.suspended_at,
                users.created_at,
                users.role,
                users.account_state,
                users.suspended_until,
                players.*
            FROM users
            LEFT JOIN players
                ON players.user_id = users.id
            WHERE users.id = ?
            """,
            (user_id,),
        ).fetchone()

        if account_row is None:
            return None

        account = dict(account_row)
        player_id = account.get("id")

        if player_id is None:
            return {
                "account": account,
                "inventory": (),
                "crime_progress": (),
                "district_reputation": (),
                "unlocked_gyms": (),
            }

        inventory = tuple(dict(row) for row in connection.execute(
            """
            SELECT item_key, quantity
            FROM player_inventory
            WHERE player_id = ?
            ORDER BY item_key
            """,
            (player_id,),
        ).fetchall())
        crime_progress = tuple(dict(row) for row in connection.execute(
            """
            SELECT crime_key, xp, attempts, successes
            FROM player_crime_progress
            WHERE player_id = ?
            ORDER BY crime_key
            """,
            (player_id,),
        ).fetchall())
        district_reputation = tuple(
            dict(row)
            for row in connection.execute(
                """
                SELECT district, reputation
                FROM player_district_reputation
                WHERE player_id = ?
                ORDER BY district
                """,
                (player_id,),
            ).fetchall()
        )
        unlocked_gyms = tuple(
            row["gym_key"]
            for row in connection.execute(
                """
                SELECT gym_key
                FROM player_unlocked_gyms
                WHERE player_id = ?
                ORDER BY gym_key
                """,
                (player_id,),
            ).fetchall()
        )

        return {
            "account": account,
            "inventory": inventory,
            "crime_progress": crime_progress,
            "district_reputation": district_reputation,
            "unlocked_gyms": unlocked_gyms,
        }
    finally:
        connection.close()



VALID_RESTRICTIONS = {"jail", "hospital"}
MAX_RESTRICTION_MINUTES = 3 * 24 * 60


def set_player_restriction(
    user_id,
    restriction,
    duration_minutes=None,
):
    if restriction == "free":
        return clear_player_restrictions(user_id)
    if restriction not in VALID_RESTRICTIONS:
        raise ValueError("Choose jail, hospital or release.")
    try:
        duration_minutes = int(duration_minutes)
    except (TypeError, ValueError):
        raise ValueError("Enter a valid duration.") from None
    if not 1 <= duration_minutes <= MAX_RESTRICTION_MINUTES:
        raise ValueError(
            "Duration must be between 1 minute and 3 days."
        )

    target_column = (
        "jail_until"
        if restriction == "jail"
        else "hospital_until"
    )
    opposing_column = (
        "hospital_until"
        if restriction == "jail"
        else "jail_until"
    )
    duration = f"+{duration_minutes} minutes"

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            f"""
            UPDATE players
            SET
                {target_column} = DATETIME(
                    CURRENT_TIMESTAMP,
                    ?
                ),
                {opposing_column} = NULL,
                travel_destination = NULL,
                travel_until = NULL
            WHERE user_id = ?
            """,
            (duration, user_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(
                "This account has no character."
            )

        until = connection.execute(
            f"""
            SELECT {target_column}
            FROM players
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        connection.commit()
        return {
            "restriction": restriction,
            "duration_minutes": duration_minutes,
            "until": until,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def clear_player_restrictions(user_id):
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            UPDATE players
            SET jail_until = NULL,
                hospital_until = NULL
            WHERE user_id = ?
            """,
            (user_id,),
        )
        connection.commit()
        if cursor.rowcount != 1:
            raise ValueError(
                "This account has no character."
            )
        return {
            "restriction": "free",
            "duration_minutes": 0,
            "until": None,
        }
    finally:
        connection.close()


# --------------------------------------------------- money and mischief

# Which live columns a prank may move, and what caps each one. Energy,
# nerve and happiness are capped per player rather than globally -- a
# top-up must not push somebody above the ceiling their level earned.
_RESOURCE_CAPS = {
    "energy": "max_energy",
    "nerve": "max_nerve",
    "happiness": "max_happiness",
    "health": "max_health",
}


def _notify(connection, player_id, message, now=None):
    """Tell the player something happened to them.

    `attack_id` is null, which the dashboard digest and `/pvp` both
    handle -- that is the same channel a burglary or a bounty uses, so
    an owner's prank arrives looking like part of the game rather than
    like a glitch.
    """
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    connection.execute(
        """
        INSERT INTO pvp_notifications (
            player_id, attack_id, message, created_at
        ) VALUES (?, NULL, ?, ?)
        """,
        (player_id, message, stamp),
    )


def _player_row(connection, user_id):
    row = connection.execute(
        """
        SELECT id, name, money, energy, max_energy, nerve, max_nerve,
               happiness, max_happiness, health, max_health,
               wanted_level, current_district
        FROM players
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    if row is None:
        raise AdminActionError("This account has no character.")

    return row


def adjust_player_money(user_id, amount, message=None):
    """Put money in a player's pocket, or take it out.

    `BEGIN IMMEDIATE` like every other money path in the game: this runs
    while the player is very likely mid-session, and an admin top-up
    landing in the middle of somebody's blackjack hand must not race it.

    A player is never pushed below zero. Asking to take more than they
    have takes what is there and says so, rather than inventing a debt
    the rest of the game has no concept of.
    """
    amount = int(amount)

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _player_row(connection, user_id)
        player_id, name, before = row[0], row[1], row[2]

        after = max(0, before + amount)
        moved = after - before

        connection.execute(
            "UPDATE players SET money = ? WHERE id = ?", (after, player_id)
        )

        if message:
            _notify(connection, player_id, message)

        connection.commit()

        return {
            "name": name,
            "requested": amount,
            "moved": moved,
            "before": before,
            "after": after,
            "clamped": moved != amount,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _scatter_district(current, rng):
    """Somewhere that is not where they are now.

    `DISTRICTS` is a tuple of definitions rather than a key map, which
    is worth reading twice: iterating it yields whole districts, and
    binding one of those into an UPDATE fails at the driver rather than
    anywhere useful.
    """
    elsewhere = [
        district.key for district in DISTRICTS if district.key != current
    ]

    return rng.choice(elsewhere) if elsewhere else current


def apply_prank(user_id, prank_key, custom_message="", rng=None):
    """Do something to a player, and tell them it happened.

    The telling is not optional. Every branch below ends in a message,
    because a change nobody explains reads as a broken game rather than
    a wind-up -- and a player cannot tell the difference from where they
    are sitting.
    """
    prank = get_prank(prank_key)

    if prank is None:
        raise AdminActionError("That is not one of the options.")

    rng = rng or random
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        (
            player_id, name, money, energy, max_energy, nerve, max_nerve,
            happiness, max_happiness, health, max_health, wanted, district,
        ) = _player_row(connection, user_id)

        current = {
            "energy": energy, "nerve": nerve, "happiness": happiness,
            "health": health, "wanted_level": wanted,
        }
        ceilings = {
            "energy": max_energy, "nerve": max_nerve,
            "happiness": max_happiness, "health": max_health,
            "wanted_level": MAX_WANTED_LEVEL,
        }

        message = prank.message
        effects = []

        if prank.custom_message:
            message = str(custom_message or "").strip()
            if not message:
                raise AdminActionError("Write something to send them.")
            if len(message) > 280:
                raise AdminActionError(
                    "Keep it under 280 characters."
                )

        # Money, from the prank's own range so nobody types a figure.
        low, high = prank.money
        if low or high:
            amount = rng.randint(low, high)
            after = max(0, money + amount)
            moved = after - money
            connection.execute(
                "UPDATE players SET money = ? WHERE id = ?", (after, player_id)
            )
            effects.append(f"£{abs(moved):,}")

            # Lifting nothing off somebody skint is still a story, but
            # it is not the story the prank was going to tell. Sending
            # "your wallet is lighter" to a player whose balance did not
            # move is the same lie this whole module exists to avoid.
            if moved == 0 and prank.foiled_message:
                message = prank.foiled_message

        # Resources, each clamped to this player's own ceiling.
        for column, delta in prank.resources.items():
            ceiling = ceilings[column]
            value = max(0, min(ceiling, current[column] + delta))
            connection.execute(
                f"UPDATE players SET {column} = ? WHERE id = ?",
                (value, player_id),
            )
            effects.append(f"{column} {current[column]} to {value}")

        if prank.scatter:
            landed = _scatter_district(district, rng)
            connection.execute(
                """
                UPDATE players
                SET current_district = ?,
                    travel_destination = NULL,
                    travel_until = NULL
                WHERE id = ?
                """,
                (landed, player_id),
            )
            message = message.format(district=get_district(landed).name)
            effects.append(f"moved to {landed}")

        _notify(connection, player_id, message)
        connection.commit()

        return {
            "name": name,
            "prank": prank,
            "message": message,
            "effects": effects,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
