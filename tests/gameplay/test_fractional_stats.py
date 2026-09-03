"""Trained stats are fractional, and combat has to cope.

`game/gym/formula.py` rounds each gain to two decimal places on
purpose, so a player who has trained has strength 84.35 rather than 84.
Combat then hands those numbers to `random.randint`, which requires an
integer.

Python hid this for years. Until 3.12 `random.randrange` accepted a
float that happened to be whole, so `randint(0, 84.0)` worked while
`randint(0, 84.35)` raised. 3.12 removed the allowance and 3.14 raises
TypeError on both.

Production runs 3.14. This sandbox runs 3.11, so the real crash cannot
be reproduced here directly -- which is exactly why every fight looked
fine locally while `/fight` returned 500 for real players.

`StrictRandom` below is the fix for that: it enforces 3.12+ rules on
whatever interpreter the suite happens to be running, so this class of
bug fails here rather than in production.
"""

import random
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from game.combat import OPPONENTS_BY_KEY, fight_opponent
from game.combat.stats import whole


class StrictRandom(random.Random):
    """A Random that rejects floats the way Python 3.12+ does.

    Do not relax this to make a test pass. It is a stand-in for the
    interpreter running in production.
    """

    def randint(self, a, b):
        for name, value in (("a", a), ("b", b)):
            if not isinstance(value, int):
                raise TypeError(
                    f"'{type(value).__name__}' object cannot be "
                    f"interpreted as an integer (randint {name}={value!r})"
                )
        return super().randint(a, b)


def trained_player(**changes):
    """A player who has actually been to the gym."""
    values = dict(
        current_district="camden",
        hospital_until=None,
        jail_until=None,
        travel_destination=None,
        shift_until=None,
        health=100,
        energy=100,
        money=0,
        xp=0,
        level=8,
        strength=84.35,
        defence=61.7,
        speed=52.05,
        dexterity=47.9,
    )
    values.update(changes)
    return SimpleNamespace(**values)


class WholeStatTests(unittest.TestCase):
    def test_a_fraction_rounds_rather_than_truncating(self):
        # 84.9 is nearly 85, and a player should not lose what they
        # trained for just because combat needs a round number.
        self.assertEqual(whole(84.9), 85)
        self.assertEqual(whole(84.35), 84)

    def test_it_is_always_an_integer(self):
        for value in (0, 10, 10.0, 84.35, 84.9, None):
            with self.subTest(value=value):
                self.assertIsInstance(whole(value), int)

    def test_a_missing_stat_is_zero_not_a_crash(self):
        self.assertEqual(whole(None), 0)


class TheStrictRandomItselfTests(unittest.TestCase):
    """The guard has to actually guard, or it proves nothing."""

    def test_it_rejects_a_whole_float(self):
        # This is the case Python 3.11 allows and 3.14 does not, and
        # the one that made the bug invisible in development.
        with self.assertRaises(TypeError):
            StrictRandom().randint(0, 10.0)

    def test_it_rejects_a_fractional_float(self):
        with self.assertRaises(TypeError):
            StrictRandom().randint(0, 10.5)

    def test_it_still_works_with_integers(self):
        self.assertIn(StrictRandom(1).randint(0, 10), range(11))


class JailWithTrainedStatsTests(unittest.TestCase):
    """The breakout reads speed and dexterity, so it is in this family.

    It never reached `randint` with a float -- the roll is `randint(1,
    100)` -- but it returned a *float chance* built from raw trained
    stats, which was then printed on the jail page as "63.0%". The
    figure is now whole, and this is the guard that keeps every
    consumer of a trained stat in one place.
    """

    def test_the_chance_is_a_whole_number(self):
        from database.repositories.jail import calculate_breakout_chance

        chance = calculate_breakout_chance(
            {"speed": 84.35, "dexterity": 219.77}, 7
        )

        self.assertIsInstance(chance, int)
        self.assertNotIsInstance(chance, bool)

    def test_the_roll_it_feeds_accepts_the_chance(self):
        """The roll is compared against it, so it has to be sane.

        Run through StrictRandom for the same reason everything else
        here is: a float creeping back in should fail on this
        interpreter rather than on the server.
        """
        from database.repositories.jail import calculate_breakout_chance

        rng = StrictRandom(7)
        chance = calculate_breakout_chance(
            {"speed": 512.44, "dexterity": 98.06}, 12
        )

        self.assertIsInstance(rng.randint(1, 100) <= chance, bool)

    def test_bail_on_a_fractional_sentence_is_whole_money(self):
        from database.repositories.jail import calculate_bail_cost

        cost = calculate_bail_cost(12, 917)

        self.assertIsInstance(cost, int)
        self.assertGreater(cost, 0)


class FightingWithTrainedStatsTests(unittest.TestCase):
    def fight(self, player, opponent_key="canal_yard_enforcer"):
        return fight_opponent(
            player,
            Mock(strength_bonus=5, defence_bonus=4),
            OPPONENTS_BY_KEY[opponent_key],
            rng=StrictRandom(99),
        )

    def test_a_trained_player_can_fight(self):
        """The production crash, reproduced under 3.12+ rules."""
        result = self.fight(trained_player())

        self.assertIsNotNone(result)

    def test_an_untrained_player_can_fight(self):
        # Whole numbers straight from the database: the case that made
        # this look fine on an older interpreter.
        result = self.fight(
            trained_player(
                strength=10.0, defence=10.0, speed=10.0, dexterity=10.0
            )
        )

        self.assertIsNotNone(result)

    def test_every_opponent_survives_a_fractional_attacker(self):
        for key in OPPONENTS_BY_KEY:
            with self.subTest(opponent=key):
                player = trained_player(
                    current_district=OPPONENTS_BY_KEY[key].district
                )
                self.assertIsNotNone(self.fight(player, key))

    def test_the_round_log_never_reports_a_fractional_hit(self):
        """"You deal 8.05 damage" is not something a player should read."""
        import re

        result = self.fight(trained_player())

        for line in result.rounds:
            for number in re.findall(r"\d+\.\d+", line):
                self.fail(f"fractional figure in the log: {line!r}")

    def test_damage_still_lands(self):
        # Rounding must not flatten combat into nothing happening.
        result = self.fight(trained_player())

        self.assertTrue(
            any("damage" in line for line in result.rounds),
            "no damage was dealt in twelve rounds",
        )


if __name__ == "__main__":
    unittest.main()
