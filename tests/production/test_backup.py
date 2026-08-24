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


if __name__ == "__main__":
    unittest.main()
