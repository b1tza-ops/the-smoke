import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from datetime import datetime, timezone
from game.crimes import commit_crime, get_crime
from game.gym import train


class GymTests(unittest.TestCase):
    def setUp(self):
        self.player = SimpleNamespace(
            energy=100,
            strength=10,
            defence=10,
            speed=10,
            dexterity=10,
            wanted_level=0,
            last_wanted_update=None,
            jail_until=None,
            hospital_until=None,
            current_district="camden",
            travel_destination=None,
            travel_until=None,
        )

    def test_strength_training_updates_strength(self):
        train(self.player, "strength")

        self.assertEqual(self.player.strength, 12)
        self.assertEqual(self.player.energy, 90)

    def test_dexterity_training_updates_dexterity(self):
        train(self.player, "dexterity")

        self.assertEqual(self.player.dexterity, 12)
        self.assertEqual(self.player.energy, 90)

    def test_jail_prevents_training(self):
        self.player.jail_until = (
            "2026-08-23 12:05:00"
        )

        now = datetime(
            2026,
            8,
            23,
            12,
            0,
            tzinfo=timezone.utc,
        )

        trained = train(
            self.player,
            "strength",
            now=now,
        )

        self.assertFalse(trained)
        self.assertEqual(
            self.player.strength,
            10,
        )
        self.assertEqual(
            self.player.energy,
            100,
        )

    def test_hospital_prevents_training(self):
        self.player.hospital_until = (
            "2026-08-23 12:05:00"
        )

        now = datetime(
            2026,
            8,
            23,
            12,
            0,
            tzinfo=timezone.utc,
        )

        trained = train(
            self.player,
            "dexterity",
            now=now,
        )

        self.assertFalse(trained)
        self.assertEqual(
            self.player.dexterity,
            10,
        )
        self.assertEqual(
            self.player.energy,
            100,
        )

    def test_travel_prevents_training(self):
        self.player.travel_destination = "soho"
        self.player.travel_until = (
            "2026-08-23 12:05:00"
        )

        now = datetime(
            2026,
            8,
            23,
            12,
            0,
            tzinfo=timezone.utc,
        )

        trained = train(
            self.player,
            "speed",
            now=now,
        )

        self.assertFalse(trained)
        self.assertEqual(
            self.player.speed,
            10,
        )
        self.assertEqual(
            self.player.energy,
            100,
        )

class CrimeTests(unittest.TestCase):
    def test_failed_crime_does_not_make_health_negative(self):
        player = SimpleNamespace(
            nerve=20,
            money=0,
            health=5,
            xp=0,
            level=1,
            crime_progress={},
            district_reputation={},
            wanted_level=0,
            last_wanted_update=None,
            jail_until=None,
            hospital_until=None,
            current_district="camden",
            travel_destination=None,
            travel_until=None,
        )

        rng = Mock()
        rng.randint.side_effect = [100, 100, 10]

        result = commit_crime(
            player,
            get_crime("camden_shoplift"),
            rng=rng,
        )

        self.assertEqual(player.health, 0)
        self.assertEqual(player.nerve, 18)
        self.assertFalse(result.success)
        self.assertEqual(result.damage, 10)

    def test_successful_crime_awards_money_xp_and_level(self):
        player = SimpleNamespace(
            nerve=20,
            money=0,
            health=100,
            xp=95,
            level=1,
            crime_progress={},
            district_reputation={},
            wanted_level=0,
            last_wanted_update=None,
            jail_until=None,
            hospital_until=None,
            current_district="camden",
            travel_destination=None,
            travel_until=None,
        )

        rng = Mock()
        rng.randint.side_effect = [1, 40]

        result = commit_crime(
            player,
            get_crime("camden_shoplift"),
            rng=rng,
        )

        self.assertEqual(player.nerve, 18)
        self.assertEqual(player.money, 40)
        self.assertEqual(player.xp, 105)
        self.assertEqual(player.level, 2)
        self.assertTrue(result.success)
        self.assertEqual(result.cash_reward, 40)


if __name__ == "__main__":
    unittest.main()