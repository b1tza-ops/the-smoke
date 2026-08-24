import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.activity import (
    get_recent_activity,
    record_activity,
)
from database.repositories.admin import (
    get_admin_player_details,
    is_user_suspended,
    set_user_suspended,
)
from database.repositories.players import create_player
from database.repositories.users import create_user


class AdminActivityPersistenceTests(unittest.TestCase):
    def test_activity_and_suspension_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "game.db"

            with patch(
                "database.core.connection.DB_PATH",
                database,
            ):
                create_tables()
                user_id = create_user(
                    "tester",
                    "tester@example.com",
                    "hash",
                )
                create_player(user_id, "Test Character")
                record_activity(
                    user_id,
                    "gym_train",
                    "Strength increased.",
                    {"gain": 2},
                )

                details = get_admin_player_details(user_id)
                self.assertIsNotNone(details)
                self.assertEqual(
                    details["account"]["username"],
                    "tester",
                )
                self.assertEqual(
                    details["account"]["name"],
                    "Test Character",
                )
                self.assertEqual(
                    {
                        row["item_key"]
                        for row in details["inventory"]
                    },
                    {"energy_drink", "first_aid_kit"},
                )
                self.assertEqual(
                    details["unlocked_gyms"],
                    ("camden_community",),
                )

                rows = get_recent_activity(
                    user_id=user_id,
                )
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0][3], "gym_train")
                self.assertFalse(
                    is_user_suspended(user_id)
                )

                self.assertTrue(
                    set_user_suspended(user_id, True)
                )
                self.assertTrue(
                    is_user_suspended(user_id)
                )

                set_user_suspended(user_id, False)
                self.assertFalse(
                    is_user_suspended(user_id)
                )


if __name__ == "__main__":
    unittest.main()
