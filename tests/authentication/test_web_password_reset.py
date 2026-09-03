import unittest
from unittest.mock import Mock, patch

from web.application import app


class WebPasswordResetTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
        )
        self.client = app.test_client()

    @patch(
        "web.application.validate_turnstile",
        return_value=True,
    )
    @patch("web.application.request_password_reset")
    def test_recovery_request_uses_generic_message(
        self,
        request_password_reset,
        validate_turnstile,
    ):
        request_password_reset.return_value = Mock(
            message=(
                "If an account exists for that email, "
                "recovery instructions will be sent."
            )
        )

        response = self.client.post(
            "/forgot-password",
            data={
                "email": "player@example.com",
                "cf-turnstile-response": "valid-token",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"If an account exists",
            response.data,
        )
        request_password_reset.assert_called_once()

    @patch(
        "web.application.reset_password",
        return_value=True,
    )
    def test_valid_reset_updates_password(
        self,
        reset_password,
    ):
        response = self.client.post(
            "/reset-password",
            data={
                "token": "reset-token",
                "password": "new-password",
                "password_confirmation": "new-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Your password has been updated.",
            response.data,
        )
        reset_password.assert_called_once_with(
            "reset-token",
            "new-password",
        )


if __name__ == "__main__":
    unittest.main()
