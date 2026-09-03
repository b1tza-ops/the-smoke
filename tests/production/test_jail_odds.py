"""The two jail formulas that stopped reading their inputs.

Both were written when a trained stat was a two-digit number, and
neither was revisited when the gym rework pushed stats into the
hundreds and thousands. They did not break loudly. They just quietly
stopped discriminating:

  Bail   cost `level * 100 + minutes * 10`, which is a flat fee bolted
         to a per-minute one. At level 20 with five minutes left it
         charged £2,050 -- £410 a minute, against about £15 a minute of
         earning power. Bail was worst value exactly when it was least
         useful, and nobody could ever rationally pay it.

  Break  `55 + speed + dexterity - level * 2`, capped at 85. Anything
  -out   above a combined 60 sat on the cap, so every trained player has
         been at 85% for months and the two stats the mechanic claims
         to read stopped mattering almost immediately.

Bail is now priced from the time it buys and the breakout from a ratio,
so both read their inputs across the whole range the game can produce.
The income model is recomputed here from the live catalogues, so a
change to the crime ladder or the careers that leaves bail behind fails
rather than drifting.
"""

import unittest

from database.repositories.jail import (
    BAIL_MINIMUM,
    BAIL_PREMIUM,
    BREAKOUT_FLOOR,
    BREAKOUT_RANGE,
    calculate_bail_cost,
    calculate_breakout_chance,
    hourly_income_estimate,
)
from game.crime import CRIMES
from game.jobs.definitions import CAREERS
from game.jobs.service import SHIFT_SECONDS
from game.world.districts import DISTRICTS_BY_KEY

# The same figure the crime curve is built on: twelve nerve an hour.
NERVE_PER_HOUR = 12

DISTRICT_LEVEL = {
    district.name: district.minimum_level
    for district in DISTRICTS_BY_KEY.values()
}


def best_hourly_income(level):
    """What the game actually offers somebody at this level, an hour.

    The best crime they can reach plus the best shift they can hold --
    which is what a player sitting in a cell is losing, since jail
    blocks both.
    """
    reachable = [
        crime for crime in CRIMES
        if DISTRICT_LEVEL.get(crime.district, 99) <= level
    ]
    crime_rate = max(
        (
            (crime.min_reward + crime.max_reward) / 2
            * (crime.success_chance / 100)
            * (NERVE_PER_HOUR / crime.nerve_cost)
            for crime in reachable
        ),
        default=0.0,
    )
    shift_rate = max(
        (
            role.salary / (SHIFT_SECONDS / 3600)
            for career in CAREERS
            for role in career.roles
            if role.required_level <= level
        ),
        default=0.0,
    )

    return crime_rate + shift_rate


class BailPricingTests(unittest.TestCase):
    def test_the_income_model_still_matches_the_catalogues(self):
        """The anti-drift test, and the reason bail can be trusted.

        `hourly_income_estimate` is a curve, not a lookup. If the crime
        ladder or the careers move and this is not redone, bail goes
        back to being priced against a game that no longer exists --
        which is how it got into the state it was in.
        """
        for level in (1, 3, 5, 7, 10, 15, 20):
            with self.subTest(level=level):
                actual = best_hourly_income(level)
                modelled = hourly_income_estimate(level)

                self.assertAlmostEqual(
                    modelled / actual, 1.0, delta=0.15,
                    msg=(
                        f"level {level}: the game offers £{actual:,.0f} "
                        f"an hour and bail is priced off £{modelled:,}"
                    ),
                )

    def test_bail_costs_about_half_again_what_the_time_is_worth(self):
        for level in (1, 5, 10, 20):
            with self.subTest(level=level):
                cost = calculate_bail_cost(level, 60 * 60)
                worth = hourly_income_estimate(level)

                self.assertAlmostEqual(
                    cost / worth, BAIL_PREMIUM, delta=0.05
                )

    def test_a_nearly_finished_sentence_is_nearly_free(self):
        """The old formula's worst case, pinned.

        £2,050 to save a level 20 player five minutes was £410 a
        minute. Whatever else changes, the last few minutes of a
        sentence must never cost more than the hour they are part of.
        """
        for level in (1, 10, 20, 40):
            with self.subTest(level=level):
                short = calculate_bail_cost(level, 5 * 60)
                whole_hour = calculate_bail_cost(level, 60 * 60)

                self.assertLess(short, whole_hour / 6)

    def test_it_never_pays_to_wait_out_a_long_sentence_instead(self):
        """Bail must stay a premium, or it becomes free time.

        Cheaper than the time is worth and every player simply buys
        their way past every sentence, and jail stops being a cost.
        """
        for level in (1, 10, 20):
            for minutes in (15, 30, 60, 180):
                with self.subTest(level=level, minutes=minutes):
                    cost = calculate_bail_cost(level, minutes * 60)
                    worth = (
                        hourly_income_estimate(level) * minutes / 60
                    )

                    self.assertGreater(cost, worth)

    def test_a_longer_sentence_always_costs_more(self):
        for level in (1, 10, 20):
            costs = [
                calculate_bail_cost(level, minutes * 60)
                for minutes in (5, 10, 30, 60, 120)
            ]

            self.assertEqual(costs, sorted(costs))
            self.assertEqual(len(set(costs)), len(costs))

    def test_a_higher_level_never_costs_less(self):
        costs = [
            calculate_bail_cost(level, 30 * 60)
            for level in range(1, 40)
        ]

        self.assertEqual(costs, sorted(costs))

    def test_it_stops_climbing_once_income_does(self):
        """Income plateaus, so bail must too.

        The old flat `level * 100` never stopped, which is why it ran
        away from the economy at the top of the game.
        """
        self.assertEqual(
            calculate_bail_cost(40, 30 * 60),
            calculate_bail_cost(400, 30 * 60),
        )

    def test_nonsense_time_is_never_free_and_never_negative(self):
        for seconds in (0, -1, -100_000):
            with self.subTest(seconds=seconds):
                self.assertEqual(
                    calculate_bail_cost(10, seconds), BAIL_MINIMUM
                )

    def test_a_levelless_player_is_still_charged(self):
        self.assertGreaterEqual(
            calculate_bail_cost(0, 30 * 60), BAIL_MINIMUM
        )
        self.assertGreaterEqual(
            calculate_bail_cost(-5, 30 * 60), BAIL_MINIMUM
        )


class BreakoutOddsTests(unittest.TestCase):
    def helper(self, skill):
        return {"speed": skill / 2, "dexterity": skill / 2}

    def test_it_is_never_certain_and_never_hopeless(self):
        for skill in (0, 10, 100, 10_000, 1_000_000):
            for level in (1, 10, 100):
                with self.subTest(skill=skill, level=level):
                    chance = calculate_breakout_chance(
                        self.helper(skill), level
                    )

                    self.assertGreaterEqual(chance, BREAKOUT_FLOOR)
                    self.assertLess(
                        chance, BREAKOUT_FLOOR + BREAKOUT_RANGE
                    )

    def test_training_still_matters_at_the_top_of_the_scale(self):
        """The whole reason this was rewritten.

        Under the old formula a combined 100 and a combined 10,000 were
        both 85%, so the stats the mechanic reads had been decorative
        for as long as anybody has been training.
        """
        lightly = calculate_breakout_chance(self.helper(100), 10)
        heavily = calculate_breakout_chance(self.helper(10_000), 10)

        self.assertGreater(heavily - lightly, 20)

    def test_more_skill_is_always_better(self):
        for level in (1, 10, 40):
            chances = [
                calculate_breakout_chance(self.helper(skill), level)
                for skill in (10, 50, 200, 1_000, 5_000)
            ]

            with self.subTest(level=level):
                self.assertEqual(chances, sorted(chances))
                self.assertEqual(len(set(chances)), len(chances))

    def test_a_higher_level_target_is_always_harder(self):
        for skill in (50, 500, 5_000):
            chances = [
                calculate_breakout_chance(self.helper(skill), level)
                for level in (1, 5, 10, 20, 40)
            ]

            with self.subTest(skill=skill):
                self.assertEqual(chances, sorted(chances, reverse=True))

    def test_trained_stats_are_floats_and_must_not_crash(self):
        """Trained stats are REAL columns, not integers.

        A float reaching `randint` is how the fight page 500'd in
        production once already, and this figure is printed on a page.
        """
        chance = calculate_breakout_chance(
            {"speed": 84.35, "dexterity": 219.77}, 7
        )

        self.assertIsInstance(chance, int)

    def test_an_untrained_player_can_still_try(self):
        self.assertEqual(
            calculate_breakout_chance(
                {"speed": 0, "dexterity": 0}, 5
            ),
            BREAKOUT_FLOOR,
        )
        self.assertEqual(
            calculate_breakout_chance(
                {"speed": -10, "dexterity": -10}, 5
            ),
            BREAKOUT_FLOOR,
        )


class HudMeterTests(unittest.TestCase):
    """Found while checking the jail page, and worth its own guard.

    The HUD works out five meter widths and renders on every page in
    the game. It used to do the arithmetic inline in the template with
    no bounds, while the routes had a clamping helper all along -- so a
    player whose XP sat below their level's floor got
    `--progress:-950%` on every page, and any meter above its maximum
    overflowed its bar.
    """

    def setUp(self):
        from web.application import percentage

        self.percentage = percentage

    def test_a_value_below_the_floor_never_goes_negative(self):
        self.assertEqual(self.percentage(-950, 100), 0)

    def test_a_value_over_the_maximum_never_overflows(self):
        self.assertEqual(self.percentage(150, 100), 100)

    def test_an_absent_maximum_is_not_a_division_by_zero(self):
        self.assertEqual(self.percentage(50, 0), 0)
        self.assertEqual(self.percentage(50, -10), 0)

    def test_it_still_reports_the_middle_honestly(self):
        self.assertEqual(self.percentage(50, 200), 25)

    def test_the_hud_uses_it_rather_than_its_own_arithmetic(self):
        """The template is where the unclamped copy lived.

        Registered as a Jinja global so the include can reach it
        without every one of the forty-odd routes passing it in.
        """
        from pathlib import Path

        from web.application import app

        self.assertIs(
            app.jinja_env.globals.get("hud_percent"), self.percentage
        )

        hud = Path(app.root_path) / "templates" / "_player_hud.html"
        markup = hud.read_text()

        self.assertEqual(markup.count("hud_percent("), 5)
        self.assertNotIn("* 100)|round", markup)


if __name__ == "__main__":
    unittest.main()
