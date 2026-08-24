#!/usr/bin/env python3
import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def backup_database(source, destination, keep):
    source = Path(source)
    destination = Path(destination)

    if not source.is_file():
        raise FileNotFoundError(
            f"Database not found: {source}"
        )

    destination.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    backup_path = (
        destination / f"the-smoke-{timestamp}.db"
    )

    source_connection = sqlite3.connect(source)
    backup_connection = sqlite3.connect(backup_path)

    try:
        source_connection.backup(backup_connection)
        result = backup_connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()

        if result is None or result[0] != "ok":
            raise RuntimeError(
                "Backup integrity check failed."
            )
    finally:
        backup_connection.close()
        source_connection.close()

    backups = sorted(
        destination.glob("the-smoke-*.db"),
        reverse=True,
    )

    for expired in backups[keep:]:
        expired.unlink()

    return backup_path


def main():
    default_source = (
        Path(__file__).resolve().parents[1]
        / "database"
        / "data"
        / "game.db"
    )
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default=os.environ.get(
            "THE_SMOKE_DB_PATH",
            default_source,
        ),
    )
    parser.add_argument(
        "--destination",
        default=os.environ.get(
            "THE_SMOKE_BACKUP_DIR",
            "/var/backups/the-smoke",
        ),
    )
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args()

    path = backup_database(
        args.source,
        args.destination,
        args.keep,
    )
    print(path)


if __name__ == "__main__":
    main()
