import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.backup_database import backup_database


class BackupTests(unittest.TestCase):
    def test_backup_is_readable_and_retention_is_applied(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "game.db"
            destination = root / "backups"
            connection = sqlite3.connect(source)
            connection.execute(
                "CREATE TABLE players (id INTEGER)"
            )
            connection.execute(
                "INSERT INTO players VALUES (7)"
            )
            connection.commit()
            connection.close()

            backup = backup_database(
                source,
                destination,
                keep=1,
            )
            restored = sqlite3.connect(backup)
            row = restored.execute(
                "SELECT id FROM players"
            ).fetchone()
            restored.close()

            self.assertEqual(row, (7,))
            self.assertEqual(
                len(list(destination.glob("*.db"))),
                1,
            )

    def test_a_backup_captures_writes_still_sitting_in_the_wal(self):
        """The one way WAL could quietly break the backups.

        Under WAL a committed write lives in `game.db-wal` until a
        checkpoint folds it into the main file, so anything that copies
        `game.db` alone can miss the most recent play. The script uses
        the online backup API, which reads through a connection and so
        sees the WAL -- this holds that, because the failure mode is
        silent and only shows up on the day someone restores.
        """
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "game.db"

            connection = sqlite3.connect(source)
            self.assertEqual(
                connection.execute(
                    "PRAGMA journal_mode = WAL"
                ).fetchone()[0],
                "wal",
            )
            connection.execute(
                "CREATE TABLE players (id INTEGER)"
            )
            connection.execute(
                "INSERT INTO players VALUES (11)"
            )
            connection.commit()

            # Hold the connection open and do not checkpoint, so the row
            # is committed but still only in the -wal file.
            self.assertTrue(
                (root / "game.db-wal").exists(),
                "expected a WAL file to exist before the backup",
            )

            backup = backup_database(
                source,
                root / "backups",
                keep=1,
            )
            connection.close()

            restored = sqlite3.connect(backup)
            row = restored.execute(
                "SELECT id FROM players"
            ).fetchone()
            restored.close()

            self.assertEqual(
                row,
                (11,),
                "the backup lost a write that was still in the WAL",
            )


if __name__ == "__main__":
    unittest.main()
