import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
)
from database.repositories.prologue import (
    choose_background,
    complete_opening_mission,
    get_or_create_prologue,
    resolve_opening_operation,
    start_opening_operation,
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
        self.assertEqual(player[12], 160)
        self.assertEqual(player[6], 160)

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

    def test_operation_persists_until_ready_then_rewards(self):
        get_or_create_prologue(self.user_id)
        choose_background(
            self.user_id,
            "former_athlete",
        )

        operation = start_opening_operation(
            self.user_id,
            "slip_through_back",
        )
        self.assertEqual(operation["style"], "Stealth")

        state = get_or_create_prologue(self.user_id)
        self.assertEqual(state["operation_stage"], "active")
        self.assertEqual(
            state["operation_approach"],
            "slip_through_back",
        )

        player = get_player_by_user_id(self.user_id)
        self.assertEqual(player[6], 152)
        self.assertEqual(player[11], 15)

        with self.assertRaises(ValueError):
            resolve_opening_operation(self.user_id)

        connection = get_connection()
        connection.execute(
            """
            UPDATE player_prologue
            SET operation_ready_at = DATETIME(
                CURRENT_TIMESTAMP,
                '-1 second'
            )
            WHERE user_id = ?
            """,
            (self.user_id,),
        )
        connection.commit()
        connection.close()

        result = resolve_opening_operation(self.user_id)
        self.assertEqual(result["cash"], 120)

        state = get_or_create_prologue(self.user_id)
        self.assertEqual(state["operation_stage"], "completed")
        self.assertEqual(state["debt_remaining"], 1575)

        player = get_player_by_user_id(self.user_id)
        self.assertEqual(player[4], 620)
        self.assertEqual(player[16], 40)
        self.assertEqual(player[17], 1)

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
