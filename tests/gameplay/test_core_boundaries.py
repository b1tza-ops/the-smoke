from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from game.crime import commit_crime, get_crime
from game.gym import train
from game.player.progression import award_xp
from game.player.regeneration import regenerate_resource


class CoreBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(
            2026,
            8,
            24,
            12,
            0,
            tzinfo=timezone.utc,
        )

    def make_player(self, **overrides):
        values = {
            "energy": 100,
            "nerve": 20,
            "health": 100,
            "money": 100,
            "xp": 0,
            "level": 1,
            "strength": 10,
            "defence": 10,
            "speed": 10,
            "dexterity": 10,
            "current_district": "camden",
            "current_gym_key": "camden_community",
            "unlocked_gyms": {"camden_community"},
            "travel_destination": None,
            "travel_until": None,
            "wanted_level": 0,
            "last_wanted_update": None,
            "jail_until": None,
            "hospital_until": None,
            "crime_progress": {},
            "district_reputation": {},
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_zero_energy_cannot_train(self):
        player = self.make_player(energy=0)

        trained = train(
            player,
            "strength",
            now=self.now,
        )

        self.assertFalse(trained)
        self.assertEqual(player.energy, 0)
        self.assertEqual(player.strength, 10)

    def test_exact_training_energy_can_reach_zero(self):
        player = self.make_player(energy=10)

        trained = train(
            player,
            "strength",
            energy=10,
            now=self.now,
        )

        self.assertTrue(trained)
        self.assertEqual(player.energy, 0)
        # Two trains, and the stat rises a little as they run.
        self.assertEqual(player.strength, 12.01)

    def test_zero_nerve_cannot_attempt_crime(self):
        player = self.make_player(nerve=0)
        rng = Mock()

        result = commit_crime(
            player,
            get_crime("camden_shoplift"),
            rng=rng,
            now=self.now,
        )

        self.assertFalse(result.attempted)
        self.assertEqual(
            result.reason,
            "not_enough_nerve",
        )
        self.assertEqual(player.nerve, 0)
        self.assertEqual(player.money, 100)
        rng.randint.assert_not_called()

    def test_exact_crime_nerve_cost_can_reach_zero(self):
        crime = get_crime("camden_shoplift")
        player = self.make_player(
            nerve=crime.nerve_cost,
        )
        rng = Mock()
        rng.randint.side_effect = [
            1,
            crime.min_reward,
        ]

        result = commit_crime(
            player,
            crime,
            rng=rng,
            now=self.now,
        )

        self.assertTrue(result.success)
        self.assertEqual(player.nerve, 0)
        self.assertEqual(
            player.money,
            100 + crime.min_reward,
        )

    def test_regeneration_waits_for_complete_tick(self):
        energy, last_update = regenerate_resource(
            current_value=0,
            maximum_value=100,
            last_update="2026-08-24 12:00:00",
            points_per_tick=5,
            tick_seconds=600,
            now=self.now + timedelta(
                minutes=9,
                seconds=59,
            ),
        )

        self.assertEqual(energy, 0)
        self.assertEqual(
            last_update,
            "2026-08-24 12:00:00",
        )

    def test_regeneration_applies_exact_tick(self):
        energy, last_update = regenerate_resource(
            current_value=0,
            maximum_value=100,
            last_update="2026-08-24 12:00:00",
            points_per_tick=5,
            tick_seconds=600,
            now=self.now + timedelta(minutes=10),
        )

        self.assertEqual(energy, 5)
        self.assertEqual(
            last_update,
            "2026-08-24 12:10:00",
        )

    def test_exact_xp_threshold_levels_player(self):
        player = self.make_player(xp=99)

        levels_gained = award_xp(player, 1)

        self.assertEqual(player.xp, 100)
        self.assertEqual(player.level, 2)
        self.assertEqual(levels_gained, 1)


if __name__ == "__main__":
    unittest.main()
