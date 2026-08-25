from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from database.core.setup import create_tables
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
    save_player,
)
from database.repositories.users import create_user
from game.crime import commit_crime, get_crime
from game.economy.bank import deposit_cash
from game.gym import train
from game.inventory import use_item
from game.jobs import (
    complete_shift,
    join_career,
    start_shift,
)
from game.player import Player
from game.world.travel import (
    start_travel,
    update_travel,
)
from utils.security import hash_password


class V1PlayerJourneyTests(unittest.TestCase):
    def test_new_player_journey_persists_end_to_end(self):
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
                    username="v1_player",
                    email="v1@example.com",
                    password_hash=hash_password(
                        "secure-password"
                    ),
                )
                create_player(
                    user_id,
                    "V1 Character",
                )
                player = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(
                    player.residence_key,
                    "tent",
                )
                self.assertEqual(
                    player.inventory,
                    {
                        "first_aid_kit": 1,
                        "energy_drink": 1,
                    },
                )

                now = datetime(
                    2026,
                    8,
                    24,
                    9,
                    0,
                    tzinfo=timezone.utc,
                )

                join_career(
                    player,
                    "construction",
                )
                start_shift(
                    player,
                    now=now,
                )
                complete_shift(
                    player,
                    now=now + timedelta(hours=3),
                )

                crime = get_crime(
                    "camden_shoplift"
                )
                rng = Mock()
                rng.randint.side_effect = [1, 40]
                commit_crime(
                    player,
                    crime,
                    rng=rng,
                    now=now + timedelta(hours=3),
                )

                trained = train(
                    player,
                    "strength",
                    energy=10,
                    now=now + timedelta(hours=3),
                )
                self.assertTrue(trained)

                save_player(player)
                deposit_cash(player, 100)

                journey = start_travel(
                    player,
                    "brixton",
                    now=now + timedelta(hours=3),
                )
                arrived = update_travel(
                    player,
                    now=now
                    + timedelta(hours=3)
                    + timedelta(minutes=10),
                )

                self.assertTrue(arrived)
                self.assertEqual(
                    journey.destination_key,
                    "brixton",
                )

                player.health = 80
                use_item(
                    player,
                    "first_aid_kit",
                )
                use_item(
                    player,
                    "energy_drink",
                )
                save_player(player)

                reloaded = Player(
                    *get_player_by_user_id(user_id)
                )

                self.assertEqual(reloaded.money, 525)
                self.assertEqual(
                    reloaded.bank_balance,
                    100,
                )
                self.assertEqual(reloaded.xp, 25)
                self.assertEqual(reloaded.level, 1)
                self.assertEqual(
                    reloaded.career_key,
                    "construction",
                )
                self.assertEqual(
                    reloaded.job_role_key,
                    "construction_labourer",
                )
                self.assertEqual(
                    reloaded.shifts_completed,
                    1,
                )
                self.assertEqual(
                    reloaded.current_district,
                    "brixton",
                )
                self.assertEqual(
                    reloaded.residence_key,
                    "tent",
                )
                # Two lightweight trains, the second at 95 happiness
                # because the first one spent 5.
                self.assertEqual(
                    reloaded.strength,
                    11.98,
                )
                self.assertEqual(reloaded.nerve, 18)
                self.assertEqual(
                    reloaded.wanted_level,
                    1,
                )
                self.assertEqual(reloaded.health, 100)
                self.assertEqual(reloaded.energy, 150)
                self.assertEqual(reloaded.inventory, {})
                self.assertIsNone(
                    reloaded.travel_destination
                )
                self.assertIsNone(
                    reloaded.travel_until
                )


if __name__ == "__main__":
    unittest.main()
