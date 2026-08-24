import unittest
from unittest.mock import ANY, patch

from web.application import app


class WebRegistrationTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
        )
        self.client = app.test_client()

    def test_login_page_links_to_registration(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Create an account", response.data)

    @patch("web.application.request_email_verification")
    @patch("web.application.create_player")
    @patch(
        "web.application.hash_password",
        return_value="hashed-password",
    )
    @patch(
        "web.application.create_user",
        return_value=42,
    )
    @patch(
        "web.application.get_user_by_email",
        return_value=None,
    )
    @patch(
        "web.application.get_user_by_username",
        return_value=None,
    )
    def test_valid_registration_requests_verification(
        self,
        get_user_by_username,
        get_user_by_email,
        create_user,
        hash_password,
        create_player,
        request_email_verification,
    ):
        response = self.client.post(
            "/register",
            data={
                "username": "New_Player",
                "email": "NEW@example.com",
                "password": "strong-pass",
                "password_confirmation": "strong-pass",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "/check-email",
        )
        create_player.assert_called_once_with(
            42,
            "New_Player",
        )
        request_email_verification.assert_called_once_with(
            user_id=42,
            email="new@example.com",
            delivery=ANY,
        )

        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)
            self.assertEqual(
                session["pending_verification_user_id"],
                42,
            )

    @patch("web.application.create_user")
    @patch("web.application.create_player")
    def test_password_confirmation_must_match(
        self,
        create_player,
        create_user,
    ):
        response = self.client.post(
            "/register",
            data={
                "username": "New_Player",
                "email": "new@example.com",
                "password": "strong-pass",
                "password_confirmation": "different-pass",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Passwords do not match.",
            response.data,
        )
        create_user.assert_not_called()
        create_player.assert_not_called()

    @patch(
        "web.application.verify_email_token",
        return_value=True,
    )
    def test_verification_link_activates_account(
        self,
        verify_email_token,
    ):
        response = self.client.get(
            "/verify-email?token=valid-token"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"Your email is verified.",
            response.data,
        )
        verify_email_token.assert_called_once_with(
            "valid-token"
        )

    @patch(
        "web.application.is_email_verified",
        return_value=False,
    )
    @patch(
        "web.application.verify_password",
        return_value=True,
    )
    @patch(
        "web.application.get_user_by_username",
        return_value=(
            7,
            "player",
            "player@example.com",
            "hash",
            "created",
        ),
    )
    def test_unverified_player_cannot_log_in(
        self,
        get_user_by_username,
        verify_password,
        is_email_verified,
    ):
        response = self.client.post(
            "/login",
            data={
                "username": "player",
                "password": "password",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            "/check-email",
        )
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)
            self.assertEqual(
                session["pending_verification_user_id"],
                7,
            )


if __name__ == "__main__":
    unittest.main()
