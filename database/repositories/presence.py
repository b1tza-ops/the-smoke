from database.core.connection import get_connection


ONLINE_WINDOW_MINUTES = 5


def mark_player_online(user_id):
    conn = get_connection()

    try:
        conn.execute(
            """
            UPDATE players
            SET last_seen = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()


def mark_player_offline(user_id):
    conn = get_connection()

    try:
        conn.execute(
            """
            UPDATE players
            SET last_seen = NULL
            WHERE user_id = ?
            """,
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()


def get_online_player_count():
    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM players
            WHERE last_seen >= datetime(
                'now',
                ?
            )
            """,
            (f"-{ONLINE_WINDOW_MINUTES} minutes",),
        ).fetchone()
        return row[0]
    finally:
        conn.close()
