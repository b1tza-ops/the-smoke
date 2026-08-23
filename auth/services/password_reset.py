import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from auth.rate_limit import enforce_rate_limit
from auth.validation import (
    ValidationError,
    normalize_email,
    validate_password,
)
from database.repositories.auth_tokens import (
    TOKEN_STATUS_CONSUMED,
    TOKEN_STATUS_EXPIRED,
    TOKEN_STATUS_USED,
    TOKEN_TYPE_EMAIL_VERIFICATION,
    TOKEN_TYPE_PASSWORD_RESET,
    consume_email_verification_token,
    consume_password_reset_token,
    create_account_token,
)
from database.repositories.users import get_user_by_email
from utils.security import hash_password, hash_token


GENERIC_RESET_MESSAGE = (
    "If an account exists for that email, "
    "recovery instructions will be sent."
)
PASSWORD_RESET_TTL_SECONDS = 30 * 60
EMAIL_VERIFICATION_TTL_SECONDS = 24 * 60 * 60


class AccountTokenError(Exception):
    """Base exception for verification and reset token failures."""


class InvalidAccountTokenError(AccountTokenError):
    """Raised when a supplied token does not exist."""


class ExpiredAccountTokenError(AccountTokenError):
    """Raised when a supplied token has expired."""


class UsedAccountTokenError(AccountTokenError):
    """Raised when a supplied token has already been used."""


@dataclass(frozen=True)
class RecoveryRequestResult:
    message: str = GENERIC_RESET_MESSAGE


def request_password_reset(
    email,
    delivery=None,
    rate_limiter=None,
    rate_key=None,
    now=None,
    token_factory=None,
):
    now = _normalise_now(now)

    try:
        normalised_email = normalize_email(email)
    except ValidationError:
        normalised_email = ""

    limiter_key = (
        rate_key
        or f"password-reset:{normalised_email or 'invalid'}"
    )
    enforce_rate_limit(
        rate_limiter,
        limiter_key,
        now=now,
    )

    user = (
        get_user_by_email(normalised_email)
        if normalised_email
        else None
    )

    if user is not None:
        raw_token, expires_at = _issue_token(
            user_id=user[0],
            token_type=TOKEN_TYPE_PASSWORD_RESET,
            ttl_seconds=PASSWORD_RESET_TTL_SECONDS,
            now=now,
            token_factory=token_factory,
        )

        if delivery is not None:
            delivery(
                user[2],
                raw_token,
                expires_at,
            )

    return RecoveryRequestResult()


def request_email_verification(
    user_id,
    email,
    delivery=None,
    rate_limiter=None,
    rate_key=None,
    now=None,
    token_factory=None,
):
    now = _normalise_now(now)
    normalised_email = normalize_email(email)
    enforce_rate_limit(
        rate_limiter,
        rate_key or f"email-verification:{user_id}",
        now=now,
    )

    raw_token, expires_at = _issue_token(
        user_id=user_id,
        token_type=TOKEN_TYPE_EMAIL_VERIFICATION,
        ttl_seconds=EMAIL_VERIFICATION_TTL_SECONDS,
        now=now,
        token_factory=token_factory,
    )

    if delivery is not None:
        delivery(
            normalised_email,
            raw_token,
            expires_at,
        )

    return expires_at


def reset_password(raw_token, new_password, now=None):
    validate_password(new_password)
    now_text = _format_timestamp(
        _normalise_now(now)
    )
    status = consume_password_reset_token(
        token_hash=hash_token(raw_token),
        password_hash=hash_password(new_password),
        now=now_text,
    )
    _raise_for_token_status(status)
    return True


def verify_email_token(raw_token, now=None):
    now_text = _format_timestamp(
        _normalise_now(now)
    )
    status = consume_email_verification_token(
        token_hash=hash_token(raw_token),
        now=now_text,
    )
    _raise_for_token_status(status)
    return True


def forgot_password():
    print("\n===== FORGOT PASSWORD =====")
    email = input("Email: ").strip()
    result = request_password_reset(email)
    print("\n" + result.message)


def _issue_token(
    user_id,
    token_type,
    ttl_seconds,
    now,
    token_factory=None,
):
    token_factory = token_factory or (
        lambda: secrets.token_urlsafe(32)
    )
    raw_token = token_factory()

    if not isinstance(raw_token, str) or not raw_token:
        raise ValueError(
            "Token factory must return non-empty text."
        )

    created_at = _format_timestamp(now)
    expires_at = _format_timestamp(
        now + timedelta(seconds=ttl_seconds)
    )

    create_account_token(
        user_id=user_id,
        token_type=token_type,
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
        created_at=created_at,
    )

    return raw_token, expires_at


def _raise_for_token_status(status):
    if status == TOKEN_STATUS_CONSUMED:
        return

    if status == TOKEN_STATUS_EXPIRED:
        raise ExpiredAccountTokenError(
            "Token has expired."
        )

    if status == TOKEN_STATUS_USED:
        raise UsedAccountTokenError(
            "Token has already been used."
        )

    raise InvalidAccountTokenError(
        "Token is invalid."
    )


def _normalise_now(now=None):
    if now is None:
        return datetime.now(timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    return now.astimezone(timezone.utc)


def _format_timestamp(timestamp):
    return timestamp.astimezone(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
