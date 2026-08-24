import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
)
from database.repositories.prologue import (
    choose_background,
    complete_opening_mission,
    get_or_create_prologue,
)
from database.repositories.users import create_user


class CamdenPrologueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        create_tables()
        self.user_id = create_user(
            "newcomer",
            "newcomer@example.com",
            "hash",
        )
        create_player(self.user_id, "Newcomer")

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def test_background_and_mission_apply_once(self):
        state = get_or_create_prologue(self.user_id)
        self.assertEqual(state["debt_remaining"], 2000)
        self.assertIsNone(state["completed_at"])

        choose_background(
            self.user_id,
            "former_athlete",
        )
        player = get_player_by_user_id(self.user_id)
        self.assertEqual(player[12], 110)
        self.assertEqual(player[6], 110)

        result = complete_opening_mission(
            self.user_id,
            "deliver_package",
        )
        self.assertEqual(result["paydown"], 350)

        state = get_or_create_prologue(self.user_id)
        self.assertEqual(state["debt_remaining"], 1650)
        self.assertIsNotNone(state["completed_at"])

        player = get_player_by_user_id(self.user_id)
        self.assertEqual(player[16], 25)
        self.assertEqual(player[17], 2)

        with self.assertRaises(ValueError):
            choose_background(
                self.user_id,
                "local_worker",
            )

        with self.assertRaises(ValueError):
            complete_opening_mission(
                self.user_id,
                "steal_watch",
            )

    def test_invalid_choices_do_not_change_progress(self):
        get_or_create_prologue(self.user_id)

        with self.assertRaises(ValueError):
            choose_background(self.user_id, "unknown")

        with self.assertRaises(ValueError):
            complete_opening_mission(
                self.user_id,
                "unknown",
            )

        state = get_or_create_prologue(self.user_id)
        self.assertIsNone(state["background"])
        self.assertEqual(state["debt_remaining"], 2000)


if __name__ == "__main__":
    unittest.main()
