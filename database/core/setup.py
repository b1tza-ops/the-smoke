from database.core.connection import get_connection
from database.core.migrations import run_migrations


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
            current_district TEXT NOT NULL DEFAULT 'camden',
            travel_destination TEXT,
            travel_until TEXT,
            residence_key TEXT NOT NULL DEFAULT 'tent'
                CHECK (TRIM(residence_key) <> ''),
            career_key TEXT,
            job_role_key TEXT,
            career_xp INTEGER NOT NULL DEFAULT 0
                CHECK (career_xp >= 0),
            shifts_completed INTEGER NOT NULL DEFAULT 0
                CHECK (shifts_completed >= 0),
            shift_started_at TEXT,
            shift_until TEXT,
            current_gym_key TEXT NOT NULL DEFAULT 'camden_community'
                CHECK (TRIM(current_gym_key) <> ''),
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)


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






    conn.commit()
    conn.close()

    run_migrations()
