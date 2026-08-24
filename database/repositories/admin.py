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
                players.last_seen
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
