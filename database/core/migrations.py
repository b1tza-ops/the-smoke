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


def migrate_009_authentication_hardening(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    existing_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(users)"
        )
    }

    if "email_verified" not in existing_columns:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN email_verified INTEGER NOT NULL
                DEFAULT 0
                CHECK (email_verified IN (0, 1))
            """
        )

    if "email_verified_at" not in existing_columns:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN email_verified_at TEXT
            """
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS account_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_type TEXT NOT NULL
                CHECK (
                    token_type IN (
                        'email_verification',
                        'password_reset'
                    )
                ),
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_account_tokens_lookup
        ON account_tokens (
            token_type,
            token_hash
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_account_tokens_user
        ON account_tokens (
            user_id,
            token_type,
            created_at
        )
        """
    )



def migrate_010_player_presence(cursor):
    add_missing_player_columns(
        cursor,
        {
            "last_seen": "TEXT",
        },
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_players_last_seen
        ON players (last_seen)
        """
    )



def migrate_011_email_verification_rollout(cursor):
    cursor.execute(
        """
        UPDATE users
        SET
            email_verified = 1,
            email_verified_at = COALESCE(
                email_verified_at,
                CURRENT_TIMESTAMP
            )
        WHERE email_verified = 0
        """
    )




def migrate_012_admin_activity_and_suspension(cursor):
    existing_user_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(users)"
        )
    }

    if "suspended_at" not in existing_user_columns:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN suspended_at TEXT
            """
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_player_activity_user_created
        ON player_activity (
            user_id,
            created_at DESC
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_player_activity_created
        ON player_activity (created_at DESC)
        """
    )


def migrate_013_alpha_growth_loop(cursor):
    existing_user_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(users)"
        )
    }

    if "is_founding_player" not in existing_user_columns:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN is_founding_player INTEGER NOT NULL
                DEFAULT 1
                CHECK (is_founding_player IN (0, 1))
            """
        )

    if "invite_code" not in existing_user_columns:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN invite_code TEXT
            """
        )

    if "referred_by_user_id" not in existing_user_columns:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN referred_by_user_id INTEGER
            """
        )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_users_invite_code
        ON users (invite_code)
        WHERE invite_code IS NOT NULL
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_users_referred_by
        ON users (referred_by_user_id)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL
                CHECK (category IN ('bug', 'idea', 'confusing', 'other')),
            message TEXT NOT NULL
                CHECK (
                    LENGTH(TRIM(message)) >= 10
                    AND LENGTH(message) <= 2000
                ),
            page_path TEXT,
            status TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'reviewed', 'closed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_player_feedback_status_created
        ON player_feedback (status, created_at DESC)
        """
    )


def migrate_014_camden_prologue(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_prologue (
            user_id INTEGER PRIMARY KEY,
            background TEXT
                CHECK (
                    background IS NULL
                    OR background IN (
                        'street_hustler',
                        'former_athlete',
                        'local_worker'
                    )
                ),
            opening_choice TEXT
                CHECK (
                    opening_choice IS NULL
                    OR opening_choice IN (
                        'deliver_package',
                        'steal_watch',
                        'refuse_offer'
                    )
                ),
            debt_remaining INTEGER NOT NULL DEFAULT 2000
                CHECK (debt_remaining >= 0),
            debt_due_at TEXT NOT NULL
                DEFAULT (
                    DATETIME(CURRENT_TIMESTAMP, '+7 days')
                ),
            outcome_text TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )


def migrate_015_operations_v1(cursor):
    columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(player_prologue)"
        )
    }

    additions = {
        "operation_stage": (
            "TEXT NOT NULL DEFAULT 'dossier'"
        ),
        "operation_started_at": "TEXT",
        "operation_ready_at": "TEXT",
        "operation_approach": "TEXT",
    }
    for name, definition in additions.items():
        if name not in columns:
            cursor.execute(
                f"""
                ALTER TABLE player_prologue
                ADD COLUMN {name} {definition}
                """
            )

    cursor.execute(
        """
        UPDATE player_prologue
        SET operation_stage = CASE
            WHEN completed_at IS NOT NULL THEN 'completed'
            WHEN opening_choice IS NOT NULL THEN 'active'
            WHEN background IS NOT NULL THEN 'briefing'
            ELSE 'dossier'
        END
        """
    )




def migrate_016_camden_corner_shop(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_cycles (
            shop_key TEXT PRIMARY KEY,
            restock_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_stock (
            shop_key TEXT NOT NULL,
            item_key TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity >= 0),
            PRIMARY KEY (shop_key, item_key),
            FOREIGN KEY (item_key) REFERENCES items(item_key) ON DELETE RESTRICT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            shop_key TEXT NOT NULL,
            item_key TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            unit_price INTEGER NOT NULL CHECK (unit_price > 0),
            total_price INTEGER NOT NULL CHECK (total_price > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY (item_key) REFERENCES items(item_key) ON DELETE RESTRICT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_shop_transactions_player
        ON shop_transactions (player_id, created_at DESC)
    """)


def migrate_017_player_equipment(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_equipment (
            player_id INTEGER NOT NULL,
            slot TEXT NOT NULL
                CHECK (slot IN ('weapon', 'armour')),
            item_key TEXT NOT NULL,
            equipped_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (player_id, slot),
            FOREIGN KEY (player_id)
                REFERENCES players(id)
                ON DELETE CASCADE,
            FOREIGN KEY (item_key)
                REFERENCES items(item_key)
                ON DELETE RESTRICT
        )
        """
    )

def migrate_018_expanded_item_catalogue(cursor):
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
            ("bottled_water", "Bottled Water", "boost", "Restores up to 10 energy.", 1, 10, "energy", 10),
            ("screwdriver", "Heavy Screwdriver", "weapon", "A common tool that offers a small combat advantage.", 0, 1, None, 0),
            ("claw_hammer", "Claw Hammer", "weapon", "A solid improvised weapon.", 0, 1, None, 0),
            ("crowbar", "Crowbar", "weapon", "Heavy steel with serious leverage.", 0, 1, None, 0),
            ("baseball_bat", "Baseball Bat", "weapon", "A weighty bat with a taped grip.", 0, 1, None, 0),
            ("machete", "Machete", "weapon", "A formidable heavy blade.", 0, 1, None, 0),
            ("leather_gloves", "Leather Gloves", "armour", "Light hand protection.", 0, 1, None, 0),
            ("work_boots", "Reinforced Work Boots", "armour", "Steel-toe boots with modest protection.", 0, 1, None, 0),
            ("motorcycle_helmet", "Motorcycle Helmet", "armour", "Strong head protection with a dark visor.", 0, 1, None, 0),
            ("heavy_coat", "Heavy Coat", "armour", "A thick coat that softens incoming blows.", 0, 1, None, 0),
            ("stab_vest", "Protective Vest", "armour", "Serious protection for dangerous streets.", 0, 1, None, 0),
        ),
    )


def migrate_019_full_equipment_slots(cursor):
    cursor.execute(
        """
        ALTER TABLE player_equipment
        RENAME TO player_equipment_legacy
        """
    )
    cursor.execute(
        """
        CREATE TABLE player_equipment (
            player_id INTEGER NOT NULL,
            slot TEXT NOT NULL CHECK (
                slot IN (
                    'primary',
                    'secondary',
                    'head',
                    'body',
                    'hands',
                    'legs',
                    'feet'
                )
            ),
            item_key TEXT NOT NULL,
            equipped_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (player_id, slot),
            FOREIGN KEY (player_id)
                REFERENCES players(id)
                ON DELETE CASCADE,
            FOREIGN KEY (item_key)
                REFERENCES items(item_key)
                ON DELETE RESTRICT
        )
        """
    )
    cursor.execute(
        """
        INSERT OR REPLACE INTO player_equipment (
            player_id,
            slot,
            item_key,
            equipped_at
        )
        SELECT
            player_id,
            CASE item_key
                WHEN 'kitchen_knife' THEN 'secondary'
                WHEN 'screwdriver' THEN 'secondary'
                WHEN 'claw_hammer' THEN 'primary'
                WHEN 'crowbar' THEN 'primary'
                WHEN 'baseball_bat' THEN 'primary'
                WHEN 'machete' THEN 'primary'
                WHEN 'leather_gloves' THEN 'hands'
                WHEN 'work_boots' THEN 'feet'
                WHEN 'motorcycle_helmet' THEN 'head'
                WHEN 'padded_jacket' THEN 'body'
                WHEN 'heavy_coat' THEN 'body'
                WHEN 'stab_vest' THEN 'body'
                WHEN 'weapon' THEN 'primary'
                ELSE 'body'
            END,
            item_key,
            equipped_at
        FROM player_equipment_legacy
        """
    )
    cursor.execute("DROP TABLE player_equipment_legacy")


def migrate_020_npc_combat_records(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_npc_combat (
            player_id INTEGER NOT NULL,
            opponent_key TEXT NOT NULL,
            wins INTEGER NOT NULL DEFAULT 0
                CHECK (wins >= 0),
            attempts INTEGER NOT NULL DEFAULT 0
                CHECK (attempts >= 0),
            last_fought_at TEXT,

            PRIMARY KEY (player_id, opponent_key),
            FOREIGN KEY (player_id)
                REFERENCES players(id)
                ON DELETE CASCADE
        )
        """
    )


def migrate_021_player_pvp(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_pvp_attacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attacker_id INTEGER NOT NULL,
            defender_id INTEGER NOT NULL,
            approach TEXT NOT NULL CHECK (
                approach IN ('aggressive', 'defensive', 'precise', 'evasive')
            ),
            outcome TEXT NOT NULL CHECK (
                outcome IN ('victory', 'defeat')
            ),
            cash_stolen INTEGER NOT NULL DEFAULT 0 CHECK (cash_stolen >= 0),
            xp_reward INTEGER NOT NULL DEFAULT 0 CHECK (xp_reward >= 0),
            reward_multiplier REAL NOT NULL DEFAULT 1
                CHECK (reward_multiplier >= 0 AND reward_multiplier <= 1),
            rounds_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (attacker_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY (defender_id) REFERENCES players(id) ON DELETE CASCADE,
            CHECK (attacker_id != defender_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pvp_attacker_target_time
        ON player_pvp_attacks(attacker_id, defender_id, created_at)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pvp_defender_time
        ON player_pvp_attacks(defender_id, created_at)
        """
    )


def migrate_022_pvp_reliability(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pvp_attack_reservations (
            defender_id INTEGER PRIMARY KEY,
            attacker_id INTEGER NOT NULL,
            reserved_at TEXT NOT NULL,
            FOREIGN KEY (defender_id)
                REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY (attacker_id)
                REFERENCES players(id) ON DELETE CASCADE,
            CHECK (defender_id != attacker_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pvp_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            attack_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            read_at TEXT,
            FOREIGN KEY (player_id)
                REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY (attack_id)
                REFERENCES player_pvp_attacks(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pvp_notifications_unread
        ON pvp_notifications(player_id, read_at, id)
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
    Migration(
        version=9,
        name="authentication_hardening",
        apply=migrate_009_authentication_hardening,
    ),
    Migration(
        version=10,
        name="player_presence",
        apply=migrate_010_player_presence,
    ),
    Migration(
        version=11,
        name="email_verification_rollout",
        apply=migrate_011_email_verification_rollout,
    ),
    Migration(
        version=12,
        name="admin_activity_and_suspension",
        apply=migrate_012_admin_activity_and_suspension,
    ),
    Migration(
        version=13,
        name="alpha_growth_loop",
        apply=migrate_013_alpha_growth_loop,
    ),
    Migration(
        version=14,
        name="camden_prologue",
        apply=migrate_014_camden_prologue,
    ),
    Migration(
        version=15,
        name="operations_v1",
        apply=migrate_015_operations_v1,
    ),
    Migration(
        version=16,
        name="camden_corner_shop",
        apply=migrate_016_camden_corner_shop,
    ),
    Migration(
        version=17,
        name="player_equipment",
        apply=migrate_017_player_equipment,
    ),
    Migration(
        version=18,
        name="expanded_item_catalogue",
        apply=migrate_018_expanded_item_catalogue,
    ),
    Migration(
        version=19,
        name="full_equipment_slots",
        apply=migrate_019_full_equipment_slots,
    ),
    Migration(
        version=20,
        name="npc_combat_records",
        apply=migrate_020_npc_combat_records,
    ),
    Migration(
        version=21,
        name="player_pvp",
        apply=migrate_021_player_pvp,
    ),
    Migration(
        version=22,
        name="pvp_reliability",
        apply=migrate_022_pvp_reliability,
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