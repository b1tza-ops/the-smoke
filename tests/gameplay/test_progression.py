import unittest
from types import SimpleNamespace

from game.player.progression import (
    award_xp,
    level_for_xp,
    max_health_for_level,
    xp_required_for_level,
)


class ProgressionTests(unittest.TestCase):
    def test_xp_requirements_for_early_levels(self):
        expected_requirements = {
            1: 0,
            2: 100,
            3: 300,
            4: 600,
            5: 1000,
        }

        for level, expected_xp in expected_requirements.items():
            with self.subTest(level=level):
                self.assertEqual(
                    xp_required_for_level(level),
                    expected_xp
                )

    def test_level_for_different_xp_values(self):
        expected_levels = {
            0: 1,
            99: 1,
            100: 2,
            299: 2,
            300: 3,
            599: 3,
            600: 4,
            1000: 5,
        }

        for xp, expected_level in expected_levels.items():
            with self.subTest(xp=xp):
                self.assertEqual(
                    level_for_xp(xp),
                    expected_level
                )

    def test_large_reward_can_gain_multiple_levels(self):
        player = SimpleNamespace(
            xp=50,
            level=1,
            strength=10,
            defence=10,
            speed=10,
            dexterity=10,
        )

        levels_gained = award_xp(player, 600)

        self.assertEqual(player.xp, 650)
        self.assertEqual(player.level, 4)
        self.assertEqual(levels_gained, 3)

        self.assertEqual(player.strength, 10)
        self.assertEqual(player.defence, 10)
        self.assertEqual(player.speed, 10)
        self.assertEqual(player.dexterity, 10)

    def test_negative_values_are_rejected(self):
        player = SimpleNamespace(xp=0, level=1)

        with self.assertRaises(ValueError):
            level_for_xp(-1)

        with self.assertRaises(ValueError):
            award_xp(player, -10)

    def test_max_health_grows_with_level(self):
        self.assertEqual(max_health_for_level(1), 100)
        self.assertEqual(max_health_for_level(4), 130)
        self.assertEqual(max_health_for_level(10), 190)

        with self.assertRaises(ValueError):
            max_health_for_level(0)

    def test_leveling_up_raises_max_health_and_tops_up_full_health(self):
        player = SimpleNamespace(
            xp=50,
            level=1,
            health=100,
            max_health=100,
        )

        levels_gained = award_xp(player, 600)

        self.assertEqual(levels_gained, 3)
        self.assertEqual(player.max_health, 130)
        self.assertEqual(player.health, 130)

    def test_leveling_up_raises_the_cap_but_not_injured_health(self):
        player = SimpleNamespace(
            xp=50,
            level=1,
            health=40,
            max_health=100,
        )

        award_xp(player, 600)

        self.assertEqual(player.max_health, 130)
        self.assertEqual(player.health, 40)

    def test_award_xp_ignores_max_health_when_player_lacks_it(self):
        player = SimpleNamespace(xp=50, level=1)

        levels_gained = award_xp(player, 600)

        self.assertEqual(levels_gained, 3)
        self.assertFalse(hasattr(player, "max_health"))


if __name__ == "__main__":
    unittest.main()
