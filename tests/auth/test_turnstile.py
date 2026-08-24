import json
import unittest
from unittest.mock import Mock, patch

from auth.turnstile import validate_turnstile


class TurnstileTests(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "TURNSTILE_SECRET_KEY": "test-secret",
            "TURNSTILE_EXPECTED_HOSTNAME": (
                "play.the-smoke.com"
            ),
        },
        clear=False,
    )
    @patch("auth.turnstile.urlopen")
    def test_valid_token_checks_hostname_and_action(
        self,
        urlopen,
    ):
        response = Mock()
        response.read.return_value = json.dumps(
            {
                "success": True,
                "hostname": "play.the-smoke.com",
                "action": "register",
            }
        ).encode()
        urlopen.return_value.__enter__.return_value = (
            response
        )

        valid = validate_turnstile(
            "browser-token",
            remote_ip="203.0.113.10",
            expected_action="register",
        )

        self.assertTrue(valid)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["response"], "browser-token")
        self.assertEqual(payload["remoteip"], "203.0.113.10")
        self.assertEqual(
            request.get_header("User-agent"),
            "the-smoke/1.0",
        )

    @patch.dict(
        "os.environ",
        {
            "TURNSTILE_SECRET_KEY": "test-secret",
            "TURNSTILE_EXPECTED_HOSTNAME": (
                "play.the-smoke.com"
            ),
        },
        clear=False,
    )
    @patch("auth.turnstile.urlopen")
    def test_wrong_hostname_fails_closed(
        self,
        urlopen,
    ):
        response = Mock()
        response.read.return_value = json.dumps(
            {
                "success": True,
                "hostname": "attacker.example",
                "action": "register",
            }
        ).encode()
        urlopen.return_value.__enter__.return_value = (
            response
        )

        self.assertFalse(
            validate_turnstile("browser-token")
        )

    @patch.dict(
        "os.environ",
        {"TURNSTILE_SECRET_KEY": "test-secret"},
        clear=False,
    )
    def test_missing_browser_token_fails_closed(self):
        self.assertFalse(validate_turnstile(""))


if __name__ == "__main__":
    unittest.main()
