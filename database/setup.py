from database.connection import get_connection


PLAYER_STATUS_COLUMNS = {
    "wanted_level": "INTEGER NOT NULL DEFAULT 0 CHECK (wanted_level >= 0)",
    "last_wanted_update": "TEXT",
    "jail_until": "TEXT",
    "hospital_until": "TEXT",
}


def ensure_player_status_columns(cursor):
    existing_columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(players)")
    }

    for column_name, definition in PLAYER_STATUS_COLUMNS.items():
        if column_name not in existing_columns:
            cursor.execute(
                f"""
                ALTER TABLE players
                ADD COLUMN {column_name} {definition}
                """
            )

    cursor.execute(
        """
        UPDATE players
        SET last_wanted_update = CURRENT_TIMESTAMP
        WHERE last_wanted_update IS NULL
        """
    )


def ensure_player_bank_column(cursor):
    existing_columns = {
        row[1]
        for row in cursor.execute("PRAGMA table_info(players)")
    }

    if "bank_balance" not in existing_columns:
        cursor.execute(
            """
            ALTER TABLE players
            ADD COLUMN bank_balance INTEGER NOT NULL DEFAULT 0
                CHECK (bank_balance >= 0)
            """
        )


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            name TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
            money INTEGER DEFAULT 500,
            bank_balance INTEGER NOT NULL DEFAULT 0
                CHECK (bank_balance >= 0),
            health INTEGER DEFAULT 100,
            energy INTEGER DEFAULT 100,
            strength INTEGER DEFAULT 10,
            defence INTEGER DEFAULT 10,
            speed INTEGER DEFAULT 10,
            dexterity INTEGER DEFAULT 10,
            nerve INTEGER DEFAULT 20,
            max_energy INTEGER NOT NULL DEFAULT 100,
            max_nerve INTEGER NOT NULL DEFAULT 20,
            last_energy_update TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_nerve_update TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            wanted_level INTEGER NOT NULL DEFAULT 0 CHECK (wanted_level >= 0),
            last_wanted_update TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            jail_until TEXT,
            hospital_until TEXT,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)
    ensure_player_status_columns(cursor)
    ensure_player_bank_column(cursor)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_crime_progress (
            player_id INTEGER NOT NULL,
            crime_key TEXT NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            successes INTEGER NOT NULL DEFAULT 0 CHECK (successes >= 0),

            PRIMARY KEY (player_id, crime_key),
            FOREIGN KEY (player_id)
                REFERENCES players(id)
                ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_district_reputation (
            player_id INTEGER NOT NULL,
            district TEXT NOT NULL,
            reputation INTEGER NOT NULL DEFAULT 0,

            PRIMARY KEY (player_id, district),
            FOREIGN KEY (player_id)
                REFERENCES players(id)
                ON DELETE CASCADE
        )
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
            idx_bank_transactions_player
        ON bank_transactions (
            player_id,
            created_at
        )
    """)

    
    conn.commit()
    conn.close()
