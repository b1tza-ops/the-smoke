import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.admin import (
    set_player_restriction,
)
from database.repositories.players import create_player
from database.repositories.users import create_user


class AdminPlayerRestrictionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        create_tables()
        self.user_id = create_user(
            "moderated",
            "moderated@example.com",
            "hash",
        )
        create_player(self.user_id, "Moderated")

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def player_status(self):
        connection = get_connection()
        row = connection.execute(
            """
            SELECT
                jail_until,
                hospital_until,
                travel_destination,
                travel_until
            FROM players
            WHERE user_id = ?
            """,
            (self.user_id,),
        ).fetchone()
        connection.close()
        return row

    def test_admin_can_jail_hospital_and_release_player(self):
        connection = get_connection()
        connection.execute(
            """
            UPDATE players
            SET
                travel_destination = 'soho',
                travel_until = DATETIME(
                    CURRENT_TIMESTAMP,
                    '+10 minutes'
                )
            WHERE user_id = ?
            """,
            (self.user_id,),
        )
        connection.commit()
        connection.close()

        jailed = set_player_restriction(
            self.user_id,
            "jail",
            4320,
        )
        self.assertEqual(jailed["restriction"], "jail")
        status = self.player_status()
        self.assertIsNotNone(status[0])
        self.assertIsNone(status[1])
        self.assertIsNone(status[2])
        self.assertIsNone(status[3])

        hospitalized = set_player_restriction(
            self.user_id,
            "hospital",
            90,
        )
        self.assertEqual(
            hospitalized["restriction"],
            "hospital",
        )
        status = self.player_status()
        self.assertIsNone(status[0])
        self.assertIsNotNone(status[1])

        released = set_player_restriction(
            self.user_id,
            "free",
        )
        self.assertEqual(released["restriction"], "free")
        status = self.player_status()
        self.assertIsNone(status[0])
        self.assertIsNone(status[1])

    def test_admin_restriction_validation(self):
        for duration in (0, 4321, "invalid", None):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    set_player_restriction(
                        self.user_id,
                        "jail",
                        duration,
                    )

        with self.assertRaises(ValueError):
            set_player_restriction(
                self.user_id,
                "unknown",
                60,
            )

    def test_account_without_character_is_rejected(self):
        account_only = create_user(
            "accountonly",
            "account@example.com",
            "hash",
        )
        with self.assertRaises(ValueError):
            set_player_restriction(
                account_only,
                "hospital",
                60,
            )


if __name__ == "__main__":
    unittest.main()
