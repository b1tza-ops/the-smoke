from dataclasses import dataclass
from datetime import datetime, timezone

from database.core.connection import get_connection


TOKEN_TYPE_EMAIL_VERIFICATION = "email_verification"
TOKEN_TYPE_PASSWORD_RESET = "password_reset"
TOKEN_TYPES = {
    TOKEN_TYPE_EMAIL_VERIFICATION,
    TOKEN_TYPE_PASSWORD_RESET,
}

TOKEN_STATUS_CONSUMED = "consumed"
TOKEN_STATUS_EXPIRED = "expired"
TOKEN_STATUS_INVALID = "invalid"
TOKEN_STATUS_USED = "used"


@dataclass(frozen=True)
class AccountToken:
    token_id: int
    user_id: int
    token_type: str
    token_hash: str
    expires_at: str
    used_at: str | None
    created_at: str


def create_account_token(
    user_id,
    token_type,
    token_hash,
    expires_at,
    created_at,
):
    if token_type not in TOKEN_TYPES:
        raise ValueError("Unknown account token type.")

    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE account_tokens
            SET used_at = ?
            WHERE
                user_id = ?
                AND token_type = ?
                AND used_at IS NULL
            """,
            (
                created_at,
                user_id,
                token_type,
            ),
        )

        cursor.execute(
            """
            INSERT INTO account_tokens (
                user_id,
                token_type,
                token_hash,
                expires_at,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                token_type,
                token_hash,
                expires_at,
                created_at,
            ),
        )

        token_id = cursor.lastrowid
        conn.commit()
        return token_id

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def consume_password_reset_token(
    token_hash,
    password_hash,
    now,
):
    return _consume_token(
        token_hash=token_hash,
        token_type=TOKEN_TYPE_PASSWORD_RESET,
        now=now,
        apply_update=lambda cursor, user_id: cursor.execute(
            """
            UPDATE users
            SET password_hash = ?
            WHERE id = ?
            """,
            (password_hash, user_id),
        ),
    )


def consume_email_verification_token(
    token_hash,
    now,
):
    return _consume_token(
        token_hash=token_hash,
        token_type=TOKEN_TYPE_EMAIL_VERIFICATION,
        now=now,
        apply_update=lambda cursor, user_id: cursor.execute(
            """
            UPDATE users
            SET
                email_verified = 1,
                email_verified_at = ?
            WHERE id = ?
            """,
            (now, user_id),
        ),
    )


def _consume_token(
    token_hash,
    token_type,
    now,
    apply_update,
):
    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                id,
                user_id,
                expires_at,
                used_at
            FROM account_tokens
            WHERE
                token_hash = ?
                AND token_type = ?
            """,
            (
                token_hash,
                token_type,
            ),
        )

        token = cursor.fetchone()

        if token is None:
            conn.rollback()
            return TOKEN_STATUS_INVALID

        token_id, user_id, expires_at, used_at = token

        if used_at is not None:
            conn.rollback()
            return TOKEN_STATUS_USED

        if _parse_timestamp(expires_at) <= _parse_timestamp(now):
            conn.rollback()
            return TOKEN_STATUS_EXPIRED

        apply_update(cursor, user_id)

        cursor.execute(
            """
            UPDATE account_tokens
            SET used_at = ?
            WHERE
                id = ?
                AND used_at IS NULL
            """,
            (
                now,
                token_id,
            ),
        )

        if cursor.rowcount != 1:
            conn.rollback()
            return TOKEN_STATUS_USED

        conn.commit()
        return TOKEN_STATUS_CONSUMED

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def _parse_timestamp(timestamp):
    parsed = datetime.fromisoformat(timestamp)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)
