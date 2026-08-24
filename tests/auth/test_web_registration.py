import unittest
from unittest.mock import patch

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
        self.assertIn(
            b"Create an account",
            response.data,
        )

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
    def test_valid_registration_creates_player_and_logs_in(
        self,
        get_user_by_username,
        get_user_by_email,
        create_user,
        hash_password,
        create_player,
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
        self.assertEqual(response.headers["Location"], "/")
        get_user_by_username.assert_called_once_with(
            "New_Player"
        )
        get_user_by_email.assert_called_once_with(
            "new@example.com"
        )
        hash_password.assert_called_once_with("strong-pass")
        create_user.assert_called_once_with(
            "New_Player",
            "new@example.com",
            "hashed-password",
        )
        create_player.assert_called_once_with(
            42,
            "New_Player",
        )

        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], 42)

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


if __name__ == "__main__":
    unittest.main()
