import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TURNSTILE_SITEVERIFY_URL = (
    "https://challenges.cloudflare.com/"
    "turnstile/v0/siteverify"
)
DEFAULT_EXPECTED_HOSTNAME = "play.the-smoke.com"


def validate_turnstile(
    token,
    remote_ip=None,
    expected_action="register",
):
    secret_key = os.environ.get(
        "TURNSTILE_SECRET_KEY",
        "",
    ).strip()

    if not secret_key or not token:
        return False

    payload = {
        "secret": secret_key,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    request = Request(
        TURNSTILE_SITEVERIFY_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "the-smoke/1.0",
        },
    )

    try:
        with urlopen(request, timeout=8) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )
    except (
        HTTPError,
        URLError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        return False

    if not result.get("success"):
        return False

    expected_hostname = os.environ.get(
        "TURNSTILE_EXPECTED_HOSTNAME",
        DEFAULT_EXPECTED_HOSTNAME,
    ).strip()

    if result.get("hostname") != expected_hostname:
        return False

    if result.get("action") != expected_action:
        return False

    return True
