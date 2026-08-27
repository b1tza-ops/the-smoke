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


def migrate_023_pvp_ratings(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_pvp_ratings (
            player_id INTEGER PRIMARY KEY,
            rating INTEGER NOT NULL DEFAULT 1000
                CHECK (rating >= 100),
            wins INTEGER NOT NULL DEFAULT 0 CHECK (wins >= 0),
            losses INTEGER NOT NULL DEFAULT 0 CHECK (losses >= 0),
            streak INTEGER NOT NULL DEFAULT 0 CHECK (streak >= 0),
            best_rating INTEGER NOT NULL DEFAULT 1000
                CHECK (best_rating >= 100),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id)
                REFERENCES players(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO player_pvp_ratings (
            player_id, rating, best_rating
        )
        SELECT id, 1000, 1000 FROM players
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pvp_rating_rank
        ON player_pvp_ratings(rating DESC, wins DESC)
        """
    )


def migrate_024_pvp_daily_contracts(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_pvp_contracts (
            player_id INTEGER NOT NULL,
            day_key TEXT NOT NULL,
            contract_key TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0
                CHECK (progress >= 0),
            claimed_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (player_id, day_key, contract_key),
            FOREIGN KEY (player_id)
                REFERENCES players(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pvp_contract_day
        ON player_pvp_contracts(day_key, contract_key)
        """
    )


def migrate_025_item_catalogue_batch_one(cursor):
    from game.inventory.items import ITEMS_BY_KEY

    item_keys = (
        "sports_drink", "painkillers", "bandage_roll", "protein_bar",
        "bolt_cutters", "glass_cutter", "burner_phone", "duct_tape",
        "police_baton", "tire_iron", "hatchet", "survival_knife",
        "denim_jacket", "hard_hat", "combat_gloves", "cargo_trousers",
        "trainers", "tactical_boots", "reinforced_jeans", "riot_helmet",
    )
    cursor.executemany(
        """
        INSERT OR IGNORE INTO items (
            item_key, name, category, description, stackable,
            max_quantity, effect_key, effect_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                item.key, item.name, item.category, item.description,
                int(item.stackable), item.max_quantity,
                item.effect_key, item.effect_amount,
            )
            for item in (ITEMS_BY_KEY[key] for key in item_keys)
        ),
    )


def migrate_026_player_happiness(cursor):
    add_missing_player_columns(
        cursor,
        {
            "happiness": (
                "INTEGER NOT NULL DEFAULT 100 "
                "CHECK (happiness >= 0)"
            ),
            "max_happiness": (
                "INTEGER NOT NULL DEFAULT 100 "
                "CHECK (max_happiness > 0)"
            ),
            "last_happiness_update": "TEXT",
        },
    )

    cursor.execute(
        """
        UPDATE players
        SET last_happiness_update = CURRENT_TIMESTAMP
        WHERE last_happiness_update IS NULL
        """
    )

    from game.inventory.items import ITEMS_BY_KEY

    item = ITEMS_BY_KEY["fish_and_chips"]
    cursor.execute(
        """
        INSERT OR IGNORE INTO items (
            item_key, name, category, description, stackable,
            max_quantity, effect_key, effect_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item.key, item.name, item.category, item.description,
            int(item.stackable), item.max_quantity,
            item.effect_key, item.effect_amount,
        ),
    )


def migrate_027_player_health_regeneration(cursor):
    add_missing_player_columns(
        cursor,
        {
            "max_health": (
                "INTEGER NOT NULL DEFAULT 100 "
                "CHECK (max_health > 0)"
            ),
            "last_health_update": "TEXT",
        },
    )

    cursor.execute(
        """
        UPDATE players
        SET last_health_update = CURRENT_TIMESTAMP
        WHERE last_health_update IS NULL
        """
    )


def migrate_028_level_scaled_max_health(cursor):
    from game.player.progression import (
        BASE_MAX_HEALTH,
        MAX_HEALTH_PER_LEVEL,
    )

    cursor.execute(
        """
        UPDATE players
        SET
            health = CASE
                WHEN health >= max_health
                THEN ? + (level - 1) * ?
                ELSE health
            END,
            max_health = ? + (level - 1) * ?
        """,
        (
            BASE_MAX_HEALTH,
            MAX_HEALTH_PER_LEVEL,
            BASE_MAX_HEALTH,
            MAX_HEALTH_PER_LEVEL,
        ),
    )


def migrate_029_admin_moderation_foundation(cursor):
    existing_user_columns = {
        row[1]
        for row in cursor.execute(
            "PRAGMA table_info(users)"
        )
    }

    if "role" not in existing_user_columns:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN role TEXT NOT NULL DEFAULT 'player'
                CHECK (role IN ('player', 'moderator', 'admin'))
            """
        )

    if "account_state" not in existing_user_columns:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN account_state TEXT NOT NULL DEFAULT 'active'
                CHECK (
                    account_state IN (
                        'active', 'suspended', 'banned'
                    )
                )
            """
        )

    if "suspended_until" not in existing_user_columns:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN suspended_until TEXT
            """
        )

    cursor.execute(
        """
        UPDATE users
        SET account_state = 'suspended'
        WHERE suspended_at IS NOT NULL
            AND account_state = 'active'
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS moderation_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER NOT NULL,
            target_user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL
                CHECK (
                    action_type IN (
                        'warn', 'suspend', 'ban', 'reverse',
                        'role_change'
                    )
                ),
            reason TEXT NOT NULL,
            previous_state TEXT NOT NULL,
            new_state TEXT NOT NULL,
            expires_at TEXT,
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (actor_user_id)
                REFERENCES users(id)
                ON DELETE RESTRICT,
            FOREIGN KEY (target_user_id)
                REFERENCES users(id)
                ON DELETE RESTRICT
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_moderation_actions_target_created
        ON moderation_actions (
            target_user_id,
            created_at DESC
        )
        """
    )


def migrate_030_operator_moderation_actions(cursor):
    """Let the server operator appear in the moderation audit trail.

    The `/admin` panel can be entered with the shared credential
    configured in the server environment, which is not tied to any
    player account. Those sessions still need to be auditable, so
    `actor_user_id` becomes nullable and a NULL actor means "server
    operator (bootstrap credential)" -- the same convention
    `player_activity` already uses for system-generated entries.

    SQLite cannot drop a NOT NULL constraint in place, so the table is
    rebuilt and its rows are copied across.
    """
    actor_column = next(
        (
            row
            for row in cursor.execute(
                "PRAGMA table_info(moderation_actions)"
            )
            if row[1] == "actor_user_id"
        ),
        None,
    )

    if actor_column is None or actor_column[3] == 0:
        return

    cursor.execute(
        """
        CREATE TABLE moderation_actions_rebuilt (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            target_user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL
                CHECK (
                    action_type IN (
                        'warn', 'suspend', 'ban', 'reverse',
                        'role_change'
                    )
                ),
            reason TEXT NOT NULL,
            previous_state TEXT NOT NULL,
            new_state TEXT NOT NULL,
            expires_at TEXT,
            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (actor_user_id)
                REFERENCES users(id)
                ON DELETE SET NULL,
            FOREIGN KEY (target_user_id)
                REFERENCES users(id)
                ON DELETE RESTRICT
        )
        """
    )

    cursor.execute(
        """
        INSERT INTO moderation_actions_rebuilt (
            id,
            actor_user_id,
            target_user_id,
            action_type,
            reason,
            previous_state,
            new_state,
            expires_at,
            created_at
        )
        SELECT
            id,
            actor_user_id,
            target_user_id,
            action_type,
            reason,
            previous_state,
            new_state,
            expires_at,
            created_at
        FROM moderation_actions
        """
    )

    cursor.execute("DROP TABLE moderation_actions")
    cursor.execute(
        """
        ALTER TABLE moderation_actions_rebuilt
        RENAME TO moderation_actions
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_moderation_actions_target_created
        ON moderation_actions (
            target_user_id,
            created_at DESC
        )
        """
    )


def migrate_031_raise_energy_capacity(cursor):
    """Raise base maximum energy from 100 to 150.

    Added rather than set, so the +10 the `former_athlete` prologue
    background grants is preserved -- those players land on 160, not
    flattened back to the base.

    Current energy is untouched; only the ceiling moves, and normal
    regeneration fills the new headroom.
    """
    cursor.execute(
        """
        UPDATE players
        SET max_energy = max_energy + 50
        """
    )


def migrate_032_operations_campaign(cursor):
    """Give operations a table of their own.

    The prologue could only ever hold one operation, because its state
    lived in the single `player_prologue` row. The campaign needs one
    record per operation, so the state moves to its own table and the
    Camden Collection each existing player ran is carried across.

    The outcome text and the paydown are stored on the record rather
    than looked up from the definitions, so a completed operation still
    describes itself even when its approach came from the retired V1
    choices.
    """
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS player_operations (
            user_id INTEGER NOT NULL,
            operation_key TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'active'
                CHECK (stage IN ('active', 'completed')),
            approach TEXT,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ready_at TEXT,
            completed_at TEXT,
            outcome_text TEXT,
            paydown INTEGER NOT NULL DEFAULT 0,

            PRIMARY KEY (user_id, operation_key),
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO player_operations (
            user_id,
            operation_key,
            stage,
            approach,
            started_at,
            ready_at,
            completed_at,
            outcome_text,
            paydown
        )
        SELECT
            user_id,
            'camden_collection',
            operation_stage,
            COALESCE(operation_approach, opening_choice),
            COALESCE(operation_started_at, created_at),
            operation_ready_at,
            completed_at,
            outcome_text,
            MAX(0, 2000 - debt_remaining)
        FROM player_prologue
        WHERE operation_stage IN ('active', 'completed')
        """
    )


def migrate_033_black_market(cursor):
    """A ledger for black market sales.

    Mirrors `shop_transactions`, which records the other direction, so
    the two halves of the item economy are auditable the same way.
    """
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fence_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            fence_key TEXT NOT NULL,
            item_key TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
            payout INTEGER NOT NULL CHECK (payout >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

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
        CREATE INDEX IF NOT EXISTS idx_fence_transactions_player
        ON fence_transactions (player_id, created_at DESC)
        """
    )


def migrate_034_item_market(cursor):
    """Listings for the global player-to-player item market.

    Items are escrowed onto the listing row rather than left in the
    seller's inventory: that is what makes it impossible to sell the
    same machete twice, or to sell one and still be carrying it.
    """
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_player_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            price_each INTEGER NOT NULL CHECK (price_each > 0),
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'sold', 'cancelled')),
            buyer_player_id INTEGER,
            commission INTEGER NOT NULL DEFAULT 0
                CHECK (commission >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            closed_at TEXT,

            FOREIGN KEY (seller_player_id)
                REFERENCES players(id)
                ON DELETE CASCADE,
            FOREIGN KEY (buyer_player_id)
                REFERENCES players(id)
                ON DELETE SET NULL,
            FOREIGN KEY (item_key)
                REFERENCES items(item_key)
                ON DELETE RESTRICT
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_listings_open
        ON market_listings (status, item_key, price_each)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_listings_seller
        ON market_listings (seller_player_id, status)
        """
    )


def migrate_035_transport_modes(cursor):
    """Remember which way a player is travelling.

    The arrival time already decides when they get there; this is so
    the page can say whether they are walking, on the bus or on the
    Underground while they are still in transit.
    """
    columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(players)")
    }

    if "travel_mode" not in columns:
        cursor.execute(
            """
            ALTER TABLE players
            ADD COLUMN travel_mode TEXT
            """
        )


def migrate_036_guns_v1(cursor):
    """Register the first four firearms.

    Shop stock and inventory rows both hold a foreign key into `items`,
    so a weapon has to exist here before the Hackney Lock-Up can put it
    on the shelf.
    """
    from game.inventory.items import ITEMS_BY_KEY

    item_keys = (
        "derringer_22",
        "converted_blank_pistol",
        "snub_nose_38",
        "compact_9mm",
    )
    cursor.executemany(
        """
        INSERT OR IGNORE INTO items (
            item_key, name, category, description, stackable,
            max_quantity, effect_key, effect_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                item.key, item.name, item.category, item.description,
                int(item.stackable), item.max_quantity,
                item.effect_key, item.effect_amount,
            )
            for item in (ITEMS_BY_KEY[key] for key in item_keys)
        ),
    )


def migrate_037_ammunition(cursor):
    """Register the three pistol calibres.

    Rounds are ordinary stackable inventory items, so like every other
    item they need a row here before a shop can sell one or a player can
    carry one. They are filed under `utility` because the items table's
    category check is closed and widening it would mean rebuilding a
    table that seven foreign keys point at.
    """
    from game.inventory.items import ITEMS_BY_KEY

    item_keys = ("ammo_22", "ammo_9mm", "ammo_38")
    cursor.executemany(
        """
        INSERT OR IGNORE INTO items (
            item_key, name, category, description, stackable,
            max_quantity, effect_key, effect_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                item.key, item.name, item.category, item.description,
                int(item.stackable), item.max_quantity,
                item.effect_key, item.effect_amount,
            )
            for item in (ITEMS_BY_KEY[key] for key in item_keys)
        ),
    )


def migrate_038_casino(cursor):
    """The Golden Square: a round log, and hands left mid-play.

    Every settled round is written to `casino_rounds` so the house edge
    can be audited against real play rather than only against the
    arithmetic in the tests.

    Blackjack is the only game that spans more than one request, so a
    hand in progress is persisted whole -- shoe included -- in
    `casino_hands`. Keeping the shoe server-side is the point: the client
    never learns the order of the undealt cards.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS casino_rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            game TEXT NOT NULL
                CHECK (game IN ('slots', 'keno', 'blackjack')),
            bet INTEGER NOT NULL CHECK (bet > 0),
            payout INTEGER NOT NULL CHECK (payout >= 0),
            detail TEXT NOT NULL DEFAULT '',
            played_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_casino_rounds_player
        ON casino_rounds (player_id, played_at)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_casino_rounds_game
        ON casino_rounds (game, played_at)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS casino_hands (
            player_id INTEGER PRIMARY KEY,
            bet INTEGER NOT NULL CHECK (bet > 0),
            shoe TEXT NOT NULL,
            cursor INTEGER NOT NULL CHECK (cursor >= 0),
            player_cards TEXT NOT NULL,
            dealer_cards TEXT NOT NULL,
            doubled INTEGER NOT NULL DEFAULT 0
                CHECK (doubled IN (0, 1)),
            opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)


def migrate_039_blackjack_splits(cursor):
    """Widen a persisted hand into a whole table.

    Splitting turns one hand into several, so the old row-per-hand shape
    cannot hold the state any more. The table is rebuilt to store the
    whole thing as JSON.

    Any hand open at the moment of the upgrade is refunded first. The
    stake left the player's pocket when the cards were dealt, and
    dropping the row without giving it back would quietly take their
    money.
    """
    open_hands = cursor.execute(
        "SELECT player_id, bet FROM casino_hands"
    ).fetchall()

    for player_id, bet in open_hands:
        cursor.execute(
            "UPDATE players SET money = money + ? WHERE id = ?",
            (bet, player_id),
        )
        cursor.execute(
            """
            INSERT INTO casino_rounds
                (player_id, game, bet, payout, detail)
            VALUES (?, 'blackjack', ?, ?, 'refunded on upgrade')
            """,
            (player_id, bet, bet),
        )

    cursor.execute("DROP TABLE IF EXISTS casino_hands")
    cursor.execute("""
        CREATE TABLE casino_hands (
            player_id INTEGER PRIMARY KEY,
            staked INTEGER NOT NULL CHECK (staked > 0),
            table_state TEXT NOT NULL,
            opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)


def migrate_040_player_clock_backfill(cursor):
    """Give every player a wanted, happiness and health clock.

    These three columns reached an upgraded database through ALTER
    TABLE, which cannot carry CURRENT_TIMESTAMP as a default, so they
    were added as plain nullable TEXT and backfilled once. Any player
    created afterwards was inserted without them and got NULL, and the
    loader raised `fromisoformat: argument must be str` on the first
    page that player opened -- an account that could be registered but
    never used.

    `create_player` now writes all three, so this only has to repair the
    accounts already stranded. A database built fresh from the CREATE
    TABLE never had the problem and has nothing to update here.
    """
    for column in (
        "last_wanted_update",
        "last_happiness_update",
        "last_health_update",
    ):
        cursor.execute(
            f"""
            UPDATE players
            SET {column} = COALESCE(
                last_energy_update,
                CURRENT_TIMESTAMP
            )
            WHERE {column} IS NULL
            """
        )


def migrate_041_loan_shark(cursor):
    """Ronnie Dell's book.

    One row per borrower, and it stays after the debt is cleared so the
    missed-payment count is remembered -- a player who defaulted once
    does not get a clean slate by paying up and borrowing again.

    Interest accrues from `interest_accrued_at` rather than on a
    schedule, the same way energy and nerve do.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_loans (
            player_id INTEGER PRIMARY KEY,
            principal INTEGER NOT NULL DEFAULT 0
                CHECK (principal >= 0),
            interest INTEGER NOT NULL DEFAULT 0
                CHECK (interest >= 0),
            missed_payments INTEGER NOT NULL DEFAULT 0
                CHECK (missed_payments >= 0),
            taken_at TEXT,
            interest_accrued_at TEXT,
            due_at TEXT,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS loan_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            kind TEXT NOT NULL
                CHECK (kind IN ('borrow', 'repay', 'interest', 'collection')),
            amount INTEGER NOT NULL,
            balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
            happened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_loan_transactions_player
        ON loan_transactions (player_id, id)
    """)


def migrate_042_operations_controls(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS operations_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            maintenance_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (maintenance_enabled IN (0, 1)),
            maintenance_starts_at TEXT,
            maintenance_ends_at TEXT,
            maintenance_title TEXT NOT NULL DEFAULT 'Maintenance in progress',
            maintenance_message TEXT NOT NULL DEFAULT
                'We are making The Smoke safer and more reliable. Please check back shortly.',
            registration_open INTEGER NOT NULL DEFAULT 1
                CHECK (registration_open IN (0, 1)),
            announcement_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (announcement_enabled IN (0, 1)),
            announcement_message TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        "INSERT OR IGNORE INTO operations_settings (id) VALUES (1)"
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
    Migration(
        version=23,
        name="pvp_ratings",
        apply=migrate_023_pvp_ratings,
    ),
    Migration(
        version=24,
        name="pvp_daily_contracts",
        apply=migrate_024_pvp_daily_contracts,
    ),
    Migration(
        version=25,
        name="item_catalogue_batch_one",
        apply=migrate_025_item_catalogue_batch_one,
    ),
    Migration(
        version=26,
        name="player_happiness",
        apply=migrate_026_player_happiness,
    ),
    Migration(
        version=27,
        name="player_health_regeneration",
        apply=migrate_027_player_health_regeneration,
    ),
    Migration(
        version=28,
        name="level_scaled_max_health",
        apply=migrate_028_level_scaled_max_health,
    ),
    Migration(
        version=29,
        name="admin_moderation_foundation",
        apply=migrate_029_admin_moderation_foundation,
    ),
    Migration(
        version=30,
        name="operator_moderation_actions",
        apply=migrate_030_operator_moderation_actions,
    ),
    Migration(
        version=31,
        name="raise_energy_capacity",
        apply=migrate_031_raise_energy_capacity,
    ),
    Migration(
        version=32,
        name="operations_campaign",
        apply=migrate_032_operations_campaign,
    ),
    Migration(
        version=33,
        name="black_market",
        apply=migrate_033_black_market,
    ),
    Migration(
        version=34,
        name="item_market",
        apply=migrate_034_item_market,
    ),
    Migration(
        version=35,
        name="transport_modes",
        apply=migrate_035_transport_modes,
    ),
    Migration(
        version=36,
        name="guns_v1",
        apply=migrate_036_guns_v1,
    ),
    Migration(
        version=37,
        name="ammunition",
        apply=migrate_037_ammunition,
    ),
    Migration(
        version=38,
        name="casino",
        apply=migrate_038_casino,
    ),
    Migration(
        version=39,
        name="blackjack_splits",
        apply=migrate_039_blackjack_splits,
    ),
    Migration(
        version=40,
        name="player_clock_backfill",
        apply=migrate_040_player_clock_backfill,
    ),
    Migration(
        version=41,
        name="loan_shark",
        apply=migrate_041_loan_shark,
    ),
    Migration(
        version=42,
        name="operations_controls",
        apply=migrate_042_operations_controls,
    ),
    Migration(version=43, name="housing_facilities", apply=lambda cursor: cursor.execute("CREATE TABLE IF NOT EXISTS player_housing_facilities (player_id INTEGER NOT NULL, facility_key TEXT NOT NULL, PRIMARY KEY (player_id, facility_key), FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE)")),
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
