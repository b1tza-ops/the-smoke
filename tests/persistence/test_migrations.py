from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from database.core.setup import create_tables


from database.core.migrations import (
    MIGRATIONS,
    Migration,
    run_migrations,
)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_dir.name) / "legacy.db"
        )

        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            self.database_path,
        )
        self.database_patch.start()

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    level INTEGER DEFAULT 1,
                    money INTEGER DEFAULT 500,
                    health INTEGER DEFAULT 100,
                    energy INTEGER DEFAULT 100,
                    strength INTEGER DEFAULT 10,
                    defence INTEGER DEFAULT 10,
                    speed INTEGER DEFAULT 10,
                    dexterity INTEGER DEFAULT 10
                )
                """
            )

            cursor.execute(
                """
                INSERT INTO players (
                    user_id,
                    name,
                    money,
                    energy
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    1,
                    "Legacy Player",
                    777,
                    25,
                ),
            )

            conn.commit()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_old_database_upgrades_without_losing_player(self):
        applied_versions = run_migrations()

        self.assertEqual(
            applied_versions,
            (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19),
        )

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(players)"
                )
            }

            self.assertTrue(
                {
                    "xp",
                    "nerve",
                    "max_energy",
                    "max_nerve",
                    "last_energy_update",
                    "last_nerve_update",
                    "wanted_level",
                    "last_wanted_update",
                    "jail_until",
                    "hospital_until",
                    "bank_balance",
                    "current_district",
                    "travel_destination",
                    "travel_until",
                    "residence_key",
                    "career_key",
                    "job_role_key",
                    "career_xp",
                    "shifts_completed",
                    "shift_started_at",
                    "shift_until",
                    "current_gym_key",
                    "last_seen",
                }.issubset(columns)
            )

            player = conn.execute(
                """
                SELECT
                    name,
                    money,
                    energy,
                    xp,
                    nerve,
                    max_energy,
                    max_nerve,
                    wanted_level,
                    bank_balance,
                    last_energy_update,
                    last_nerve_update,
                    current_district,
                    travel_destination,
                    travel_until,
                    residence_key,
                    career_key,
                    job_role_key,
                    career_xp,
                    shifts_completed,
                    shift_started_at,
                    shift_until,
                    current_gym_key
                FROM players
                WHERE user_id = 1
                """
            ).fetchone()

            self.assertEqual(
                player[:9],
                (
                    "Legacy Player",
                    777,
                    25,
                    0,
                    20,
                    100,
                    20,
                    0,
                    0,
                ),
            )
            self.assertIsNotNone(player[9])
            self.assertIsNotNone(player[10])

            self.assertEqual(
                player[11:],
                (
                    "camden",
                    None,
                    None,
                    "tent",
                    None,
                    None,
                    0,
                    0,
                    None,
                    None,
                    "camden_community",
                ),
            )

            migrations = conn.execute(
                """
                SELECT version, name
                FROM schema_migrations
                ORDER BY version
                """
            ).fetchall()

            self.assertEqual(
                migrations,
                [
                    (
                        1,
                        "player_progression_and_resources",
                    ),
                    (2, "player_status"),
                    (3, "bank_system"),
                    (
                        4,
                        "london_districts_and_travel",
                    ),
                    (
                        5,
                        "starting_housing",
                    ),
                    (6, "legal_jobs"),
                    (7, "district_gyms"),
                    (8, "starter_inventory"),
                    (9, "authentication_hardening"),
                    (10, "player_presence"),
                    (
                        11,
                        "email_verification_rollout",
                    ),
                    (
                        12,
                        "admin_activity_and_suspension",
                    ),
                    (
                        13,
                        "alpha_growth_loop",
                    ),
                    (
                        14,
                        "camden_prologue",
                    ),
                    (
                        15,
                        "operations_v1",
                    ),
                    (
                        16,
                        "camden_corner_shop",
                    ),
                    (17, "player_equipment"),
                    (18, "expanded_item_catalogue"),
                    (19, "full_equipment_slots"),
                ],
            )

            bank_table = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE
                    type = 'table'
                    AND name = 'bank_transactions'
                """
            ).fetchone()

            self.assertEqual(
                bank_table,
                ("bank_transactions",),
            )

            gym_access = conn.execute(
                """
                SELECT player_id, gym_key
                FROM player_unlocked_gyms
                ORDER BY player_id, gym_key
                """
            ).fetchall()

            self.assertEqual(
                gym_access,
                [(1, "camden_community")],
            )

            item_rows = conn.execute(
                """
                SELECT item_key, category
                FROM items
                ORDER BY item_key
                """
            ).fetchall()

            self.assertEqual(len(item_rows), 16)

            starter_inventory = conn.execute(
                """
                SELECT item_key, quantity
                FROM player_inventory
                WHERE player_id = 1
                ORDER BY item_key
                """
            ).fetchall()

            self.assertEqual(
                starter_inventory,
                [
                    ("energy_drink", 1),
                    ("first_aid_kit", 1),
                ],
            )

            user_columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(users)"
                )
            }
            token_table = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE
                    type = 'table'
                    AND name = 'account_tokens'
                """
            ).fetchone()

            self.assertIn("email_verified", user_columns)
            self.assertIn("email_verified_at", user_columns)
            self.assertIn("is_founding_player", user_columns)
            self.assertIn("invite_code", user_columns)
            self.assertIn("referred_by_user_id", user_columns)
            self.assertEqual(
                token_table,
                ("account_tokens",),
            )

    def test_full_loadout_slots_accept_equipment_writes(self):
        run_migrations()

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            conn.execute(
                """
                INSERT INTO player_inventory (
                    player_id,
                    item_key,
                    quantity
                )
                VALUES (?, ?, ?)
                """,
                (1, "machete", 1),
            )
            conn.execute(
                """
                INSERT INTO player_equipment (
                    player_id,
                    slot,
                    item_key
                )
                VALUES (?, ?, ?)
                """,
                (1, "primary", "machete"),
            )
            equipped = conn.execute(
                """
                SELECT slot, item_key
                FROM player_equipment
                WHERE player_id = ?
                """,
                (1,),
            ).fetchone()

        self.assertEqual(equipped, ("primary", "machete"))

    def test_running_migrations_twice_is_safe(self):
        first_run = run_migrations()
        second_run = run_migrations()

        self.assertEqual(
            first_run,
            (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19),
        )
        self.assertEqual(second_run, ())

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            player_count = conn.execute(
                "SELECT COUNT(*) FROM players"
            ).fetchone()[0]

            money = conn.execute(
                """
                SELECT money
                FROM players
                WHERE user_id = 1
                """
            ).fetchone()[0]

            migration_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM schema_migrations
                """
            ).fetchone()[0]

            player_columns = [
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(players)"
                )
            ]

            self.assertEqual(player_count, 1)
            self.assertEqual(money, 777)
            self.assertEqual(migration_count, 19)
            self.assertEqual(
                len(player_columns),
                len(set(player_columns)),
            )
    def test_failed_migration_rolls_back(self):
        run_migrations()

        def broken_migration(cursor):
            cursor.execute(
                """
                ALTER TABLE players
                ADD COLUMN temporary_value INTEGER
                """
            )

            raise RuntimeError("Migration failed")

        failing_migration = Migration(
            version=20,
            name="deliberately_broken_migration",
            apply=broken_migration,
        )

        with patch(
            "database.core.migrations.MIGRATIONS",
            MIGRATIONS + (failing_migration,),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Migration failed",
            ):
                run_migrations()

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(players)"
                )
            }

            recorded_versions = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT version
                    FROM schema_migrations
                    ORDER BY version
                    """
                )
            ]

            money = conn.execute(
                """
                SELECT money
                FROM players
                WHERE user_id = 1
                """
            ).fetchone()[0]

            self.assertNotIn(
                "temporary_value",
                columns,
            )
            self.assertEqual(
                recorded_versions,
                [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
            )
            self.assertEqual(money, 777)

    def test_create_tables_runs_migrations_automatically(self):
        create_tables()
        create_tables()

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            versions = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT version
                    FROM schema_migrations
                    ORDER BY version
                    """
                )
            ]

            player_count = conn.execute(
                "SELECT COUNT(*) FROM players"
            ).fetchone()[0]

            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(players)"
                )
            }

            self.assertEqual(
                versions,
                [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
            )
            self.assertEqual(player_count, 1)
            self.assertIn("bank_balance", columns)
            self.assertIn("wanted_level", columns)
            self.assertIn("current_district", columns)
            self.assertIn("travel_destination", columns)
            self.assertIn("travel_until", columns)
            self.assertIn("residence_key", columns)
            self.assertIn("career_key", columns)
            self.assertIn("job_role_key", columns)
            self.assertIn("career_xp", columns)
            self.assertIn("shifts_completed", columns)
            self.assertIn("shift_started_at", columns)
            self.assertIn("shift_until", columns)
            self.assertIn("current_gym_key", columns)
            self.assertIn("last_seen", columns)

            user_columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(users)"
                )
            }
            self.assertIn("email_verified", user_columns)
            self.assertIn("email_verified_at", user_columns)
            self.assertIn("is_founding_player", user_columns)
            self.assertIn("invite_code", user_columns)
            self.assertIn("referred_by_user_id", user_columns)

    def test_bank_schema_is_created_by_migration_three(self):
        with patch(
            "database.core.migrations.MIGRATIONS",
            MIGRATIONS[:3],
        ):
            applied_versions = run_migrations()

        self.assertEqual(
            applied_versions,
            (1, 2, 3),
        )

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            bank_table = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE
                    type = 'table'
                    AND name = 'bank_transactions'
                """
            ).fetchone()

            bank_index = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE
                    type = 'index'
                    AND name = 'idx_bank_transactions_player'
                """
            ).fetchone()

            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(players)"
                )
            }

        self.assertEqual(
            bank_table,
            ("bank_transactions",),
        )
        self.assertEqual(
            bank_index,
            ("idx_bank_transactions_player",),
        )
        self.assertNotIn(
            "current_district",
            columns,
        )

if __name__ == "__main__":
    unittest.main()