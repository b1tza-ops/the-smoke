import unittest
from unittest.mock import Mock, patch

from auth.email_delivery import send_verification_email


class ResendEmailDeliveryTests(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "RESEND_API_KEY": "test-key",
            "THE_SMOKE_EMAIL_FROM": (
                "The Smoke "
                "<no-reply@account.the-smoke.com>"
            ),
            "THE_SMOKE_PUBLIC_URL": (
                "https://play.the-smoke.com"
            ),
        },
        clear=False,
    )
    @patch("auth.email_delivery.urlopen")
    def test_request_identifies_application(
        self,
        urlopen,
    ):
        response = Mock()
        response.status = 200
        response.read.return_value = b'{"id": "email-id"}'
        urlopen.return_value.__enter__.return_value = (
            response
        )

        result = send_verification_email(
            "player@example.com",
            "raw-token",
            "2026-08-25 06:00:00",
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.get_header("User-agent"),
            "the-smoke/1.0",
        )
        self.assertEqual(result["id"], "email-id")


if __name__ == "__main__":
    unittest.main()
