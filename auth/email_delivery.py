import json
import os
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from utils.security import hash_token


RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_PUBLIC_URL = "https://play.the-smoke.com"
DEFAULT_EMAIL_FROM = (
    "The Smoke <no-reply@account.the-smoke.com>"
)


class EmailDeliveryError(RuntimeError):
    """Raised when a transactional email cannot be delivered."""


def send_verification_email(email, raw_token, expires_at):
    verification_url = _account_url(
        "verify-email",
        raw_token,
    )
    safe_url = escape(verification_url, quote=True)

    return _send_email(
        email=email,
        subject="Verify your email for The Smoke",
        html=(
            "<div style=\"font-family:Arial,sans-serif;"
            "max-width:560px;margin:auto;color:#17210d\">"
            "<h1>Welcome to The Smoke</h1>"
            "<p>Confirm your email to activate your account "
            "and enter London.</p>"
            f"<p><a href=\"{safe_url}\" "
            "style=\"display:inline-block;background:#b9f34b;"
            "color:#12170c;padding:14px 20px;"
            "border-radius:8px;font-weight:700;"
            "text-decoration:none\">Verify email</a></p>"
            f"<p>This link expires at {escape(expires_at)} UTC."
            "</p><p>If you did not create this account, "
            "you can ignore this email.</p></div>"
        ),
        text=(
            "Welcome to The Smoke. Verify your email by "
            f"opening this link: {verification_url}\n\n"
            f"This link expires at {expires_at} UTC."
        ),
        idempotency_key=(
            "email-verification-"
            f"{hash_token(raw_token)}"
        ),
    )


def send_password_reset_email(email, raw_token, expires_at):
    reset_url = _account_url(
        "reset-password",
        raw_token,
    )
    safe_url = escape(reset_url, quote=True)

    return _send_email(
        email=email,
        subject="Reset your password for The Smoke",
        html=(
            "<div style=\"font-family:Arial,sans-serif;"
            "max-width:560px;margin:auto;color:#17210d\">"
            "<h1>Reset your password</h1>"
            "<p>Someone requested a password reset for "
            "your account.</p>"
            f"<p><a href=\"{safe_url}\" "
            "style=\"display:inline-block;background:#b9f34b;"
            "color:#12170c;padding:14px 20px;"
            "border-radius:8px;font-weight:700;"
            "text-decoration:none\">Reset password</a></p>"
            f"<p>This link expires at {escape(expires_at)} UTC."
            "</p><p>If you did not request this, ignore "
            "this email. Your password remains unchanged."
            "</p></div>"
        ),
        text=(
            "Reset your password for The Smoke by opening "
            f"this link: {reset_url}\n\n"
            f"This link expires at {expires_at} UTC. "
            "Ignore this message if you did not request it."
        ),
        idempotency_key=(
            "password-reset-"
            f"{hash_token(raw_token)}"
        ),
    )


def _account_url(path, raw_token):
    public_url = os.environ.get(
        "THE_SMOKE_PUBLIC_URL",
        DEFAULT_PUBLIC_URL,
    ).rstrip("/")
    return (
        f"{public_url}/{path}"
        f"?token={quote(raw_token, safe='')}"
    )


def _send_email(
    email,
    subject,
    html,
    text,
    idempotency_key,
):
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender = os.environ.get(
        "THE_SMOKE_EMAIL_FROM",
        DEFAULT_EMAIL_FROM,
    ).strip()

    if not api_key:
        raise EmailDeliveryError(
            "Resend API key is not configured."
        )

    payload = {
        "from": sender,
        "to": [email],
        "subject": subject,
        "html": html,
        "text": text,
    }
    request = Request(
        RESEND_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "the-smoke/1.0",
            "Idempotency-Key": idempotency_key,
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            if response.status not in (200, 201):
                raise EmailDeliveryError(
                    "Resend rejected the email."
                )
            return json.loads(
                response.read().decode("utf-8")
            )
    except (HTTPError, URLError, TimeoutError) as error:
        raise EmailDeliveryError(
            "Email could not be sent."
        ) from error
