from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from game.world.travel import start_travel
from game.player.status import (
    add_wanted,
    send_to_hospital,
    send_to_jail,
)

from database.repositories.players import (
    create_player,
    get_player_by_user_id,
    save_player,
)
from database.core.setup import create_tables
from database.repositories.users import create_user
from game.player import Player
from game.player.progression import award_xp
from game.crime import commit_crime, get_crime

from game.economy.bank import deposit_cash, withdraw_cash
from game.housing import purchase_residence
from game.jobs import complete_shift, join_career, start_shift
from game.gym import select_gym, unlock_gym


class PlayerPersistenceTests(unittest.TestCase):
    def test_xp_and_level_persist_across_sessions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "data" / "game.db"

            with patch("database.core.connection.DB_PATH", database_path):
                create_tables()

                user_id = create_user(
                    username="test_player",
                    email="test@example.com",
                    password_hash="test_hash"
                )

                create_player(user_id, "Test Character")

                player_data = get_player_by_user_id(user_id)
                player = Player(*player_data)

                levels_gained = award_xp(player, 650)
                save_player(player)

                reloaded_data = get_player_by_user_id(user_id)
                reloaded_player = Player(*reloaded_data)

                self.assertEqual(levels_gained, 3)
                self.assertEqual(reloaded_player.xp, 650)
                self.assertEqual(reloaded_player.level, 4)

                self.assertEqual(reloaded_player.strength, 10)
                self.assertEqual(reloaded_player.defence, 10)
                self.assertEqual(reloaded_player.speed, 10)
                self.assertEqual(reloaded_player.dexterity, 10)

    def test_crime_progress_and_district_reputation_persist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "data" / "game.db"

            with patch("database.core.connection.DB_PATH", database_path):
                create_tables()

                user_id = create_user(
                    username="crime_player",
                    email="crime@example.com",
                    password_hash="test_hash"
                )
                create_player(user_id, "Crime Character")

                player = Player(*get_player_by_user_id(user_id))
                crime = get_crime("camden_shoplift")
                rng = Mock()
                rng.randint.side_effect = [1, 40]

                commit_crime(player, crime, rng=rng)
                save_player(player)

                reloaded = Player(*get_player_by_user_id(user_id))

                self.assertEqual(
                    reloaded.crime_progress[crime.key],
                    {
                        "xp": crime.crime_xp_reward,
                        "attempts": 1,
                        "successes": 1,
                    },
                )
                self.assertEqual(
                    reloaded.district_reputation["Camden"],
                    crime.reputation_reward,
                )



    def test_player_status_survives_reload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "data" / "game.db"

            with patch("database.core.connection.DB_PATH", database_path):
                create_tables()

                user_id = create_user(
                    username="status_player",
                    email="status@example.com",
                    password_hash="test_hash",
                )

                create_player(user_id, "Status Character")
                player = Player(*get_player_by_user_id(user_id))

                now = datetime(
                    2026,
                    8,
                    22,
                    14,
                    0,
                    tzinfo=timezone.utc,
                )

                add_wanted(
                    player,
                    amount=7,
                    now=now,
                )

                send_to_jail(
                    player,
                    duration_seconds=300,
                    now=now,
                )

                send_to_hospital(
                    player,
                    duration_seconds=600,
                    now=now,
                )

                save_player(player)

                reloaded = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(reloaded.wanted_level, 7)
                self.assertEqual(
                    reloaded.last_wanted_update,
                    "2026-08-22 14:00:00",
                )
                self.assertEqual(
                    reloaded.jail_until,
                    "2026-08-22 14:05:00",
                )
                self.assertEqual(
                    reloaded.hospital_until,
                    "2026-08-22 14:10:00",
                )


    def test_bank_balances_persist_across_sessions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "data" / "game.db"

            with patch("database.core.connection.DB_PATH", database_path):
                create_tables()

                user_id = create_user(
                    username="bank_player",
                    email="bank@example.com",
                    password_hash="test_hash",
                )

                create_player(user_id, "Bank Character")
                player = Player(*get_player_by_user_id(user_id))

                deposit_cash(player, 200)
                save_player(player)

                reloaded = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(reloaded.money, 300)
                self.assertEqual(reloaded.bank_balance, 200)

                withdraw_cash(reloaded, 50)
                save_player(reloaded)

                reloaded_again = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(reloaded_again.money, 350)
                self.assertEqual(
                    reloaded_again.bank_balance,
                    150,
                )

    def test_active_travel_survives_reload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = (
                Path(temp_dir) / "data" / "game.db"
            )

            with patch(
                "database.core.connection.DB_PATH",
                database_path,
            ):
                create_tables()

                user_id = create_user(
                    username="travel_player",
                    email="travel@example.com",
                    password_hash="test_hash",
                )

                create_player(
                    user_id,
                    "Travel Character",
                )

                player = Player(
                    *get_player_by_user_id(user_id)
                )

                now = datetime.now(timezone.utc)

                journey = start_travel(
                    player,
                    "brixton",
                    now=now,
                )

                save_player(player)

                reloaded = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(
                    reloaded.current_district,
                    "camden",
                )
                self.assertEqual(
                    reloaded.travel_destination,
                    "brixton",
                )
                self.assertEqual(
                    reloaded.travel_until,
                    journey.arrives_at,
                )
                self.assertEqual(
                    reloaded.money,
                    465,
                )


    def test_residence_persists_across_sessions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = (
                Path(temp_dir) / "data" / "game.db"
            )

            with patch(
                "database.core.connection.DB_PATH",
                database_path,
            ):
                create_tables()

                user_id = create_user(
                    username="housing_player",
                    email="housing@example.com",
                    password_hash="test_hash",
                )

                create_player(
                    user_id,
                    "Housing Character",
                )

                player = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(
                    player.residence_key,
                    "tent",
                )

                purchase_residence(
                    player,
                    "hostel",
                )
                save_player(player)

                reloaded = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(
                    reloaded.residence_key,
                    "hostel",
                )
                self.assertEqual(reloaded.money, 250)

    def test_job_progress_and_active_shift_persist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = (
                Path(temp_dir) / "data" / "game.db"
            )

            with patch(
                "database.core.connection.DB_PATH",
                database_path,
            ):
                create_tables()

                user_id = create_user(
                    username="job_player",
                    email="job@example.com",
                    password_hash="test_hash",
                )
                create_player(user_id, "Job Character")

                player = Player(
                    *get_player_by_user_id(user_id)
                )
                now = datetime.now(timezone.utc)

                join_career(player, "construction")
                shift = start_shift(player, now=now)
                save_player(player)

                reloaded = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(
                    reloaded.career_key,
                    "construction",
                )
                self.assertEqual(
                    reloaded.job_role_key,
                    "construction_labourer",
                )
                self.assertEqual(
                    reloaded.shift_until,
                    shift.completes_at,
                )
                self.assertEqual(reloaded.energy, 90)

                complete_shift(
                    reloaded,
                    now=now + timedelta(hours=3),
                )
                save_player(reloaded)

                completed = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(completed.money, 620)
                self.assertEqual(completed.xp, 15)
                self.assertEqual(completed.career_xp, 15)
                self.assertEqual(completed.shifts_completed, 1)
                self.assertIsNone(completed.shift_started_at)
                self.assertIsNone(completed.shift_until)

    def test_gym_access_and_selection_persist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = (
                Path(temp_dir) / "data" / "game.db"
            )

            with patch(
                "database.core.connection.DB_PATH",
                database_path,
            ):
                create_tables()

                user_id = create_user(
                    username="gym_player",
                    email="gym@example.com",
                    password_hash="test_hash",
                )
                create_player(user_id, "Gym Character")

                player = Player(
                    *get_player_by_user_id(user_id)
                )
                player.level = 2
                player.money = 1_000
                player.current_district = "brixton"

                unlock_gym(
                    player,
                    "brixton_performance",
                )
                select_gym(
                    player,
                    "brixton_performance",
                )
                save_player(player)

                reloaded = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(
                    reloaded.current_gym_key,
                    "brixton_performance",
                )
                self.assertIn(
                    "camden_community",
                    reloaded.unlocked_gyms,
                )
                self.assertIn(
                    "brixton_performance",
                    reloaded.unlocked_gyms,
                )
                self.assertEqual(reloaded.money, 250)

if __name__ == "__main__":
    unittest.main()
