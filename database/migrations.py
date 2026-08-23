import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from database.connection import get_connection


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Cursor], None]


def get_player_columns(cursor):
    return {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(players)"
        )
    }


def add_missing_player_columns(cursor, column_definitions):
    existing_columns = get_player_columns(cursor)

    for column_name, definition in column_definitions.items():
        if column_name in existing_columns:
            continue

        cursor.execute(
            f"""
            ALTER TABLE players
            ADD COLUMN {column_name} {definition}
            """
        )


def migrate_001_player_progression_and_resources(cursor):
    add_missing_player_columns(
        cursor,
        {
            "xp": "INTEGER NOT NULL DEFAULT 0",
            "nerve": "INTEGER DEFAULT 20",
            "max_energy": "INTEGER NOT NULL DEFAULT 100",
            "max_nerve": "INTEGER NOT NULL DEFAULT 20",
            "last_energy_update": "TEXT",
            "last_nerve_update": "TEXT",
        },
    )

    cursor.execute(
        """
        UPDATE players
        SET last_energy_update = CURRENT_TIMESTAMP
        WHERE last_energy_update IS NULL
        """
    )

    cursor.execute(
        """
        UPDATE players
        SET last_nerve_update = CURRENT_TIMESTAMP
        WHERE last_nerve_update IS NULL
        """
    )


def migrate_002_player_status(cursor):
    add_missing_player_columns(
        cursor,
        {
            "wanted_level": (
                "INTEGER NOT NULL DEFAULT 0 "
                "CHECK (wanted_level >= 0)"
            ),
            "last_wanted_update": "TEXT",
            "jail_until": "TEXT",
            "hospital_until": "TEXT",
        },
    )

    cursor.execute(
        """
        UPDATE players
        SET last_wanted_update = CURRENT_TIMESTAMP
        WHERE last_wanted_update IS NULL
        """
    )


def migrate_003_bank_system(cursor):
    add_missing_player_columns(
        cursor,
        {
            "bank_balance": (
                "INTEGER NOT NULL DEFAULT 0 "
                "CHECK (bank_balance >= 0)"
            ),
        },
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bank_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL
                CHECK (
                    transaction_type IN (
                        'deposit',
                        'withdrawal'
                    )
                ),
            amount INTEGER NOT NULL
                CHECK (amount > 0),
            cash_balance_after INTEGER NOT NULL
                CHECK (cash_balance_after >= 0),
            bank_balance_after INTEGER NOT NULL
                CHECK (bank_balance_after >= 0),
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (player_id)
                REFERENCES players(id)
                ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_bank_transactions_player
        ON bank_transactions (
            player_id,
            created_at
        )
        """
    )
    
MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="player_progression_and_resources",
        apply=migrate_001_player_progression_and_resources,
    ),
    Migration(
        version=2,
        name="player_status",
        apply=migrate_002_player_status,
    ),
    Migration(
        version=3,
        name="bank_system",
        apply=migrate_003_bank_system,
    ),
)
def ensure_migration_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY
                CHECK (version > 0),
            name TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def get_applied_versions(cursor):
    return {
        row[0]
        for row in cursor.execute(
            "SELECT version FROM schema_migrations"
        )
    }


def run_migrations():
    conn = get_connection()
    applied_now = []

    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()

        ensure_migration_table(cursor)
        applied_versions = get_applied_versions(cursor)

        for migration in MIGRATIONS:
            if migration.version in applied_versions:
                continue

            migration.apply(cursor)

            cursor.execute(
                """
                INSERT INTO schema_migrations (
                    version,
                    name
                )
                VALUES (?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                ),
            )

            applied_now.append(migration.version)

        conn.commit()
        return tuple(applied_now)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()