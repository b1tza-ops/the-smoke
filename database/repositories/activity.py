import json

from database.core.connection import get_connection


def record_activity(
    user_id,
    action_type,
    summary,
    metadata=None,
):
    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT INTO player_activity (
                user_id,
                action_type,
                summary,
                metadata_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                action_type,
                summary,
                json.dumps(
                    metadata or {},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def get_recent_activity(user_id=None, limit=50):
    connection = get_connection()

    try:
        if user_id is None:
            rows = connection.execute(
                """
                SELECT
                    activity.id,
                    activity.user_id,
                    users.username,
                    activity.action_type,
                    activity.summary,
                    activity.metadata_json,
                    activity.created_at
                FROM player_activity AS activity
                LEFT JOIN users
                    ON users.id = activity.user_id
                ORDER BY activity.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT
                    activity.id,
                    activity.user_id,
                    users.username,
                    activity.action_type,
                    activity.summary,
                    activity.metadata_json,
                    activity.created_at
                FROM player_activity AS activity
                LEFT JOIN users
                    ON users.id = activity.user_id
                WHERE activity.user_id = ?
                ORDER BY activity.id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

        return tuple(rows)
    finally:
        connection.close()
