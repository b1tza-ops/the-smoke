import secrets
import sqlite3

from database.core.connection import get_connection


def ensure_invite_code(user_id):
    connection = get_connection()

    try:
        row = connection.execute(
            "SELECT invite_code FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            return None

        if row[0]:
            return row[0]

        for _ in range(5):
            code = secrets.token_hex(4).upper()

            try:
                connection.execute(
                    """
                    UPDATE users
                    SET invite_code = ?
                    WHERE id = ? AND invite_code IS NULL
                    """,
                    (code, user_id),
                )
                connection.commit()
                saved = connection.execute(
                    "SELECT invite_code FROM users WHERE id = ?",
                    (user_id,),
                ).fetchone()
                return saved[0]
            except sqlite3.IntegrityError:
                connection.rollback()

        raise RuntimeError("Could not generate a unique invite code.")
    finally:
        connection.close()


def apply_referral(user_id, invite_code):
    code = (invite_code or "").strip().upper()

    if not code:
        return False

    connection = get_connection()

    try:
        inviter = connection.execute(
            "SELECT id FROM users WHERE invite_code = ?",
            (code,),
        ).fetchone()

        if inviter is None or inviter[0] == user_id:
            return False

        cursor = connection.execute(
            """
            UPDATE users
            SET referred_by_user_id = ?
            WHERE id = ? AND referred_by_user_id IS NULL
            """,
            (inviter[0], user_id),
        )
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


def get_growth_profile(user_id):
    invite_code = ensure_invite_code(user_id)
    connection = get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                is_founding_player,
                (
                    SELECT COUNT(*)
                    FROM users AS referred
                    WHERE referred.referred_by_user_id = users.id
                )
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

        if row is None:
            return None

        return {
            "is_founding_player": bool(row[0]),
            "invite_code": invite_code,
            "referral_count": row[1],
        }
    finally:
        connection.close()


def submit_feedback(user_id, category, message, page_path=None):
    category = (category or "").strip().lower()
    message = (message or "").strip()

    if category not in {"bug", "idea", "confusing", "other"}:
        raise ValueError("Choose a valid feedback category.")

    if len(message) < 10:
        raise ValueError("Please provide at least 10 characters.")

    if len(message) > 2000:
        raise ValueError("Feedback must be 2,000 characters or fewer.")

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT INTO player_feedback (
                user_id,
                category,
                message,
                page_path
            )
            VALUES (?, ?, ?, ?)
            """,
            (user_id, category, message, page_path),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def get_recent_feedback(limit=100):
    connection = get_connection()

    try:
        return tuple(connection.execute(
            """
            SELECT
                player_feedback.id,
                users.username,
                player_feedback.category,
                player_feedback.message,
                player_feedback.page_path,
                player_feedback.status,
                player_feedback.created_at
            FROM player_feedback
            JOIN users
                ON users.id = player_feedback.user_id
            ORDER BY player_feedback.id DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        ).fetchall())
    finally:
        connection.close()
