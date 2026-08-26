import os
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(
    os.environ.get(
        "THE_SMOKE_DB_PATH",
        BASE_DIR / "data" / "game.db",
    )
)

# How long a connection waits for a lock before giving up. This is the
# sqlite3 default made explicit: with several workers serving a game
# where every page load writes, it is worth being able to see and tune.
BUSY_TIMEOUT_SECONDS = 5.0

# Databases this process has already put into WAL mode. The setting is
# persistent -- it lives in the database file, not the connection -- so
# running the pragma on every connection costs about 200us to be told
# what it was already told. That is five times the cost of opening the
# connection at all, and a single page load opens several.
_WAL_APPLIED = set()


def _enable_wal(conn, path):
    """Put the database into write-ahead logging, once per process.

    The default rollback journal takes a database-wide exclusive lock to
    write, so a writer blocks every reader and vice versa. This game
    writes on *every* page load -- `get_player_by_user_id` settles the
    regeneration clocks before it returns -- so under more than one
    worker the whole site serialises behind whoever is writing.

    Under WAL, readers and the writer no longer block each other. Two
    writers still serialise, which is what BUSY_TIMEOUT_SECONDS is for.

    The pragma reports the mode it ended up in rather than raising, so a
    database that cannot take WAL -- a network filesystem, a read-only
    mount -- keeps working on the old journal instead of failing to open.
    """
    mode = conn.execute(
        "PRAGMA journal_mode = WAL"
    ).fetchone()

    if mode and mode[0].lower() == "wal":
        _WAL_APPLIED.add(path)


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    path = str(DB_PATH)
    conn = sqlite3.connect(
        DB_PATH,
        timeout=BUSY_TIMEOUT_SECONDS,
    )

    if path not in _WAL_APPLIED:
        _enable_wal(conn, path)

    conn.execute("PRAGMA foreign_keys = ON")

    return conn
