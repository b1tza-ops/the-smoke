import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.connection import get_connection


class ConnectionTests(unittest.TestCase):
    def test_connection_creates_missing_data_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "data" / "game.db"

            with patch("database.core.connection.DB_PATH", database_path):
                conn = get_connection()
                foreign_keys_enabled = conn.execute(
                    "PRAGMA foreign_keys"
                ).fetchone()[0]
                conn.close()

            self.assertTrue(database_path.exists())
            self.assertEqual(foreign_keys_enabled, 1)


if __name__ == "__main__":
    unittest.main()
