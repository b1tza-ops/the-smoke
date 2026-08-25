from database.core.connection import get_connection


def get_user_role(user_id):
    connection = get_connection()

    try:
        row = connection.execute(
            "SELECT role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def get_account_state(user_id):
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT account_state, suspended_until
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)
    finally:
        connection.close()


def count_active_admins():
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE role = 'admin'
                AND account_state = 'active'
            """,
        ).fetchone()
        return row[0]
    finally:
        connection.close()


def set_user_role(user_id, role):
    connection = get_connection()

    try:
        cursor = connection.execute(
            "UPDATE users SET role = ? WHERE id = ?",
            (role, user_id),
        )
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


def apply_account_state(
    user_id,
    new_state,
    suspended_until=None,
):
    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            UPDATE users
            SET account_state = ?,
                suspended_until = ?
            WHERE id = ?
            """,
            (new_state, suspended_until, user_id),
        )
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


def record_moderation_action(
    actor_user_id,
    target_user_id,
    action_type,
    reason,
    previous_state,
    new_state,
    expires_at=None,
):
    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT INTO moderation_actions (
                actor_user_id,
                target_user_id,
                action_type,
                reason,
                previous_state,
                new_state,
                expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor_user_id,
                target_user_id,
                action_type,
                reason,
                previous_state,
                new_state,
                expires_at,
            ),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def get_moderation_history(target_user_id):
    connection = get_connection()

    try:
        return tuple(
            connection.execute(
                """
                SELECT
                    id,
                    actor_user_id,
                    target_user_id,
                    action_type,
                    reason,
                    previous_state,
                    new_state,
                    expires_at,
                    created_at
                FROM moderation_actions
                WHERE target_user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (target_user_id,),
            ).fetchall()
        )
    finally:
        connection.close()
