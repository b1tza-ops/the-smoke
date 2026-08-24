from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.presence import (
    get_online_player_count,
    mark_player_offline,
    mark_player_online,
)


class PlayerPresenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_dir.name) / "presence.db"
        )
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            self.database_path,
        )
        self.database_patch.start()
        create_tables()

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            conn.executemany(
                """
                INSERT INTO users (
                    username,
                    email,
                    password_hash
                )
                VALUES (?, ?, ?)
                """,
                (
                    ("player-one", "one@example.com", "hash"),
                    ("player-two", "two@example.com", "hash"),
                ),
            )
            conn.executemany(
                """
                INSERT INTO players (user_id, name)
                VALUES (?, ?)
                """,
                (
                    (1, "Player One"),
                    (2, "Player Two"),
                ),
            )
            conn.commit()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_only_recently_active_players_are_online(self):
        mark_player_online(1)

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            conn.execute(
                """
                UPDATE players
                SET last_seen = datetime('now', '-6 minutes')
                WHERE user_id = 2
                """
            )
            conn.commit()

        self.assertEqual(get_online_player_count(), 1)

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            conn.execute(
                """
                UPDATE players
                SET last_seen = datetime('now', '-4 minutes')
                WHERE user_id = 2
                """
            )
            conn.commit()

        self.assertEqual(get_online_player_count(), 2)

    def test_logging_out_marks_player_offline_immediately(self):
        mark_player_online(1)
        self.assertEqual(get_online_player_count(), 1)

        mark_player_offline(1)

        self.assertEqual(get_online_player_count(), 0)


if __name__ == "__main__":
    unittest.main()
