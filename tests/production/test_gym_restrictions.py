import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
)
from database.repositories.users import create_user
from game.gym import TrainingRestrictedError, train
from game.player import Player
from game.player.status import send_to_hospital, send_to_jail


class GymRestrictionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        create_tables()
        user_id = create_user(
            "patient",
            "patient@example.com",
            "hash",
        )
        create_player(user_id, "Patient")
        self.player = Player(
            *get_player_by_user_id(user_id)
        )

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def assert_training_is_blocked(self):
        energy_before = self.player.energy
        strength_before = self.player.strength

        with self.assertRaises(TrainingRestrictedError):
            train(
                self.player,
                "strength",
                energy=10,
                gym_key="camden_community",
            )

        self.assertEqual(self.player.energy, energy_before)
        self.assertEqual(
            self.player.strength,
            strength_before,
        )

    def test_hospital_blocks_training(self):
        send_to_hospital(self.player, 600)
        self.assert_training_is_blocked()

    def test_jail_blocks_training(self):
        send_to_jail(self.player, 600)
        self.assert_training_is_blocked()


if __name__ == "__main__":
    unittest.main()
