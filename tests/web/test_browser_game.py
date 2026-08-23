import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.players import get_player_by_user_id
from game.player import Player
from web.application import app


class BrowserGameTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = (
            Path(self.temp_dir.name)
            / "data"
            / "game.db"
        )
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            database_path,
        )
        self.database_patch.start()
        create_tables()

        app.config.update(
            TESTING=True,
            SECRET_KEY="browser-test-secret",
        )
        self.client = app.test_client()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def csrf_from(self, response):
        match = re.search(
            rb'name="_csrf_token" value="([^"]+)"',
            response.data,
        )
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def register_and_create_character(self):
        response = self.client.get("/register")
        token = self.csrf_from(response)
        response = self.client.post(
            "/register",
            data={
                "_csrf_token": token,
                "username": "browser_player",
                "email": "browser@example.com",
                "password": "safe-password",
                "password_confirm": "safe-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["Location"].endswith(
                "/character/create"
            )
        )

        response = self.client.get("/character/create")
        token = self.csrf_from(response)
        response = self.client.post(
            "/character/create",
            data={
                "_csrf_token": token,
                "name": "Web Player",
            },
        )
        self.assertEqual(response.status_code, 302)

    def current_player(self):
        with self.client.session_transaction() as browser_session:
            user_id = browser_session["user_id"]
        return Player(*get_player_by_user_id(user_id))

    def test_new_player_can_register_and_open_every_v1_page(self):
        self.register_and_create_character()

        for path in (
            "/",
            "/gym",
            "/crimes",
            "/jobs",
            "/inventory",
            "/bank",
            "/travel",
            "/housing",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"The Smoke", response.data)

    def test_state_changing_request_requires_csrf_token(self):
        self.register_and_create_character()

        response = self.client.post(
            "/bank/deposit",
            data={"amount": "100"},
        )

        self.assertEqual(response.status_code, 400)
        player = self.current_player()
        self.assertEqual(player.money, 500)
        self.assertEqual(player.bank_balance, 0)

    def test_bank_and_gym_actions_persist(self):
        self.register_and_create_character()

        bank_page = self.client.get("/bank")
        token = self.csrf_from(bank_page)
        response = self.client.post(
            "/bank/deposit",
            data={
                "_csrf_token": token,
                "amount": "100",
            },
        )
        self.assertEqual(response.status_code, 302)

        gym_page = self.client.get("/gym")
        token = self.csrf_from(gym_page)
        response = self.client.post(
            "/gym/train",
            data={
                "_csrf_token": token,
                "stat": "strength",
                "energy": "20",
            },
        )
        self.assertEqual(response.status_code, 302)

        player = self.current_player()
        self.assertEqual(player.money, 400)
        self.assertEqual(player.bank_balance, 100)
        self.assertEqual(player.energy, 80)
        self.assertEqual(player.strength, 14)


if __name__ == "__main__":
    unittest.main()
