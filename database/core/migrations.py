import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from database.core.connection import get_connection


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


def migrate_004_london_districts_and_travel(cursor):
    add_missing_player_columns(
        cursor,
        {
            "current_district": (
                "TEXT NOT NULL DEFAULT 'camden'"
            ),
            "travel_destination": "TEXT",
            "travel_until": "TEXT",
        },
    )

    cursor.execute(
        """
        UPDATE players
        SET current_district = 'camden'
        WHERE
            current_district IS NULL
            OR TRIM(current_district) = ''
        """
    )


def migrate_005_starting_housing(cursor):
    add_missing_player_columns(
        cursor,
        {
            "residence_key": (
                "TEXT NOT NULL DEFAULT 'tent' "
                "CHECK (TRIM(residence_key) <> '')"
            ),
        },
    )

    cursor.execute(
        """
        UPDATE players
        SET residence_key = 'tent'
        WHERE
            residence_key IS NULL
            OR TRIM(residence_key) = ''
        """
    )


def migrate_006_legal_jobs(cursor):
    add_missing_player_columns(
        cursor,
        {
            "career_key": "TEXT",
            "job_role_key": "TEXT",
            "career_xp": (
                "INTEGER NOT NULL DEFAULT 0 "
                "CHECK (career_xp >= 0)"
            ),
            "shifts_completed": (
                "INTEGER NOT NULL DEFAULT 0 "
                "CHECK (shifts_completed >= 0)"
            ),
            "shift_started_at": "TEXT",
            "shift_until": "TEXT",
        },
    )


def migrate_007_district_gyms(cursor):
    add_missing_player_columns(
        cursor,
        {
            "current_gym_key": (
                "TEXT NOT NULL DEFAULT 'camden_community' "
                "CHECK (TRIM(current_gym_key) <> '')"
            ),
        },
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_unlocked_gyms (
            player_id INTEGER NOT NULL,
            gym_key TEXT NOT NULL,
            unlocked_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (player_id, gym_key),
            FOREIGN KEY (player_id)
                REFERENCES players(id)
                ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO player_unlocked_gyms (
            player_id,
            gym_key
        )
        SELECT id, 'camden_community'
        FROM players
        """
    )


def migrate_008_starter_inventory(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            item_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL
                CHECK (
                    category IN (
                        'medical',
                        'boost',
                        'weapon',
                        'armour',
                        'utility'
                    )
                ),
            description TEXT NOT NULL,
            stackable INTEGER NOT NULL
                CHECK (stackable IN (0, 1)),
            max_quantity INTEGER NOT NULL
                CHECK (max_quantity > 0),
            effect_key TEXT,
            effect_amount INTEGER NOT NULL DEFAULT 0
                CHECK (effect_amount >= 0)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_inventory (
            player_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            quantity INTEGER NOT NULL
                CHECK (quantity > 0),

            PRIMARY KEY (player_id, item_key),
            FOREIGN KEY (player_id)
                REFERENCES players(id)
                ON DELETE CASCADE,
            FOREIGN KEY (item_key)
                REFERENCES items(item_key)
                ON DELETE RESTRICT
        )
        """
    )

    cursor.executemany(
        """
        INSERT OR IGNORE INTO items (
            item_key,
            name,
            category,
            description,
            stackable,
            max_quantity,
            effect_key,
            effect_amount
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                "first_aid_kit",
                "First Aid Kit",
                "medical",
                "Restores up to 25 health.",
                1,
                5,
                "health",
                25,
            ),
            (
                "energy_drink",
                "Energy Drink",
                "boost",
                "Restores up to 20 energy.",
                1,
                5,
                "energy",
                20,
            ),
            (
                "kitchen_knife",
                "Kitchen Knife",
                "weapon",
                "A basic close-range weapon.",
                0,
                1,
                None,
                0,
            ),
            (
                "padded_jacket",
                "Padded Jacket",
                "armour",
                "Basic protection for a new player.",
                0,
                1,
                None,
                0,
            ),
            (
                "lockpick",
                "Lockpick",
                "utility",
                "A simple tool for future crime actions.",
                1,
                20,
                None,
                0,
            ),
        ),
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO player_inventory (
            player_id,
            item_key,
            quantity
        )
        SELECT id, 'first_aid_kit', 1
        FROM players
        """
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO player_inventory (
            player_id,
            item_key,
            quantity
        )
        SELECT id, 'energy_drink', 1
        FROM players
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
    Migration(
        version=4,
        name="london_districts_and_travel",
        apply=migrate_004_london_districts_and_travel,
    ),
    Migration(
        version=5,
        name="starting_housing",
        apply=migrate_005_starting_housing,
    ),
    Migration(
        version=6,
        name="legal_jobs",
        apply=migrate_006_legal_jobs,
    ),
    Migration(
        version=7,
        name="district_gyms",
        apply=migrate_007_district_gyms,
    ),
    Migration(
        version=8,
        name="starter_inventory",
        apply=migrate_008_starter_inventory,
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