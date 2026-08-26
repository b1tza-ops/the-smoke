import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.connection import (
    BUSY_TIMEOUT_SECONDS,
    _WAL_APPLIED,
    get_connection,
)


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


class WriteAheadLoggingTests(unittest.TestCase):
    """Readers and the writer must stop blocking each other.

    Every page load in this game writes -- the loader settles the
    regeneration clocks before it returns -- so on the default rollback
    journal, where a writer takes a database-wide exclusive lock, more
    than one worker serialises the whole site behind whoever is writing.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = (
            Path(self.temp_dir.name) / "game.db"
        )
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            self.database_path,
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        _WAL_APPLIED.discard(str(self.database_path))

    def test_a_connection_opens_the_database_in_wal(self):
        conn = get_connection()
        try:
            mode = conn.execute(
                "PRAGMA journal_mode"
            ).fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(mode, "wal")

    def test_the_mode_sticks_without_being_reapplied(self):
        # The pragma costs about five times what opening the connection
        # does, and a page load opens several, so it must not run every
        # time. It does not need to: the mode lives in the file.
        get_connection().close()

        self.assertIn(str(self.database_path), _WAL_APPLIED)

        plain = sqlite3.connect(self.database_path)
        try:
            mode = plain.execute(
                "PRAGMA journal_mode"
            ).fetchone()[0]
        finally:
            plain.close()

        self.assertEqual(mode, "wal")

    def test_an_open_reader_does_not_block_a_write_from_committing(self):
        writer = get_connection()
        writer.execute("CREATE TABLE t (id INTEGER)")
        writer.commit()

        reader = get_connection()
        try:
            # A reader part-way through its own transaction, which is
            # every request that is still rendering.
            reader.execute("BEGIN")
            reader.execute("SELECT count(*) FROM t").fetchone()

            # On a rollback journal the commit cannot take the exclusive
            # lock while that reader holds a shared one, so this raises
            # "database is locked" once the busy timeout runs out. Under
            # WAL it goes through immediately.
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("INSERT INTO t VALUES (1)")
            writer.commit()
        finally:
            reader.rollback()
            reader.close()
            writer.close()

        settled = get_connection()
        try:
            rows = settled.execute(
                "SELECT count(*) FROM t"
            ).fetchone()[0]
        finally:
            settled.close()

        self.assertEqual(rows, 1)

    def test_a_lock_is_waited_on_rather_than_failing_instantly(self):
        conn = get_connection()
        try:
            timeout_ms = conn.execute(
                "PRAGMA busy_timeout"
            ).fetchone()[0]
        finally:
            conn.close()

        self.assertEqual(
            timeout_ms,
            int(BUSY_TIMEOUT_SECONDS * 1000),
        )


if __name__ == "__main__":
    unittest.main()
