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
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    sender = os.environ.get(
        "THE_SMOKE_EMAIL_FROM",
        DEFAULT_EMAIL_FROM,
    ).strip()
    public_url = os.environ.get(
        "THE_SMOKE_PUBLIC_URL",
        DEFAULT_PUBLIC_URL,
    ).rstrip("/")

    if not api_key:
        raise EmailDeliveryError(
            "Resend API key is not configured."
        )

    verification_url = (
        f"{public_url}/verify-email"
        f"?token={quote(raw_token, safe='')}"
    )
    safe_url = escape(verification_url, quote=True)

    payload = {
        "from": sender,
        "to": [email],
        "subject": "Verify your email for The Smoke",
        "html": (
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
        "text": (
            "Welcome to The Smoke. Verify your email by "
            f"opening this link: {verification_url}\n\n"
            f"This link expires at {expires_at} UTC."
        ),
    }

    request = Request(
        RESEND_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "the-smoke/1.0",
            "Idempotency-Key": (
                "email-verification-"
                f"{hash_token(raw_token)}"
            ),
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            if response.status not in (200, 201):
                raise EmailDeliveryError(
                    "Resend rejected the verification email."
                )
            return json.loads(
                response.read().decode("utf-8")
            )

    except (HTTPError, URLError, TimeoutError) as error:
        raise EmailDeliveryError(
            "Verification email could not be sent."
        ) from error
