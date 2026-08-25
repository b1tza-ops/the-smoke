import sqlite3

from database.core.connection import get_connection


def get_admin_player_overview():
    connection = get_connection()

    try:
        return tuple(connection.execute(
            """
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
            ORDER BY users.id DESC
            """
        ).fetchall())
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
