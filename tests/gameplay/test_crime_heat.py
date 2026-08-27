"""Heat, and what a big job really costs.

`wanted_level` accrued on every crime, decayed over time, sat in the
HUD on a 0-100 scale, and was read by nothing at all. Meanwhile the
risk of a serious crime was paid in dead time: five days inside for a
canal handover, which made it worth £9 an hour against £221 for the
starter crime. Nobody had a reason to leave Camden.

Heat is the cost now. A big score does not punish the job you just
pulled; it makes the next one riskier, and it bleeds off while you do
anything else. That is what these hold.
"""

import random
import unittest
from types import SimpleNamespace

from game.crime import CRIMES, CRIMES_BY_KEY
from game.crime.progression import (
    MAX_HEAT_JAIL_INCREASE,
    jail_chance_with_heat,
)
from game.player.status import (
    MAX_WANTED_LEVEL,
    WANTED_DECAY_POINTS,
    WANTED_DECAY_SECONDS,
)


class HeatRuleTests(unittest.TestCase):
    def test_a_clean_sheet_leaves_the_odds_alone(self):
        self.assertEqual(jail_chance_with_heat(20, 0), 20)

    def test_heat_sharpens_the_odds(self):
        self.assertGreater(
            jail_chance_with_heat(20, MAX_WANTED_LEVEL),
            jail_chance_with_heat(20, 0),
        )

    def test_the_worst_case_is_the_stated_one(self):
        # Gentle on purpose: half again as likely at the cap, not
        # double. Heat is meant to pace a run, not end it.
        self.assertEqual(
            jail_chance_with_heat(20, MAX_WANTED_LEVEL),
            round(20 * (1 + MAX_HEAT_JAIL_INCREASE)),
        )

    def test_it_climbs_the_whole_way(self):
        chances = [
            jail_chance_with_heat(20, heat)
            for heat in range(0, MAX_WANTED_LEVEL + 1, 10)
        ]

        self.assertEqual(chances, sorted(chances))

    def test_it_never_promises_more_than_certainty(self):
        self.assertLessEqual(
            jail_chance_with_heat(90, MAX_WANTED_LEVEL),
            100,
        )

    def test_nonsense_heat_is_survived(self):
        for bad in (None, -50, 10_000):
            with self.subTest(wanted_level=bad):
                self.assertGreaterEqual(
                    jail_chance_with_heat(20, bad),
                    20,
                )


class SentenceLadderTests(unittest.TestCase):
    def test_a_heavier_job_keeps_you_longer(self):
        ordered = sorted(CRIMES, key=lambda c: c.nerve_cost)
        sentences = [c.jail_seconds for c in ordered]

        self.assertEqual(sentences, sorted(sentences))

    def test_no_sentence_is_longer_than_an_evening(self):
        # The point of the change: the top tiers ran to five days.
        for crime in CRIMES:
            with self.subTest(crime=crime.key):
                self.assertLessEqual(crime.jail_seconds, 60 * 60)


class HeatPacingTests(unittest.TestCase):
    """The numbers that make this a pacing loop rather than a wall."""

    def heat_per_hour(self, crime):
        nerve_per_hour = 12
        return crime.wanted_gain * (nerve_per_hour / crime.nerve_cost)

    def decay_per_hour(self):
        return 3600 / WANTED_DECAY_SECONDS * WANTED_DECAY_POINTS

    def test_the_starter_crime_can_be_run_forever(self):
        # Camden generates heat at exactly the rate it bleeds off, so
        # the safe wage never becomes unavailable.
        self.assertLessEqual(
            self.heat_per_hour(CRIMES_BY_KEY["camden_shoplift"]),
            self.decay_per_hour(),
        )

    def test_the_big_jobs_build_heat_faster_than_it_falls(self):
        for key in (
            "shoreditch_gallery_lift",
            "shoreditch_server_room",
            "hackney_canal_handover",
        ):
            with self.subTest(crime=key):
                self.assertGreater(
                    self.heat_per_hour(CRIMES_BY_KEY[key]),
                    self.decay_per_hour(),
                    f"{key} can be run indefinitely with no cost",
                )

    def test_heat_costs_a_player_something_measurable(self):
        crime = CRIMES_BY_KEY["hackney_canal_handover"]
        cold = jail_chance_with_heat(crime.jail_chance, 0)
        hot = jail_chance_with_heat(crime.jail_chance, MAX_WANTED_LEVEL)

        self.assertGreaterEqual(hot - cold, 5)


class HeatThroughACrimeTests(unittest.TestCase):
    """It has to reach the dice, not just the arithmetic."""

    def player(self, wanted_level):
        return SimpleNamespace(
            wanted_level=wanted_level,
            level=10,
            money=1_000,
            energy=100,
            nerve=100,
            happiness=100,
            max_happiness=100,
            inventory={},
            residence_key="tent",
            crime_progress={},
            district_reputation={},
            current_district="camden",
            jail_until=None,
            hospital_until=None,
            travel_destination=None,
            travel_until=None,
            last_wanted_update=None,
            last_happiness_update=None,
            last_energy_update=None,
            last_nerve_update=None,
            max_energy=150,
            max_nerve=100,
            health=100,
            max_health=100,
            xp=0,
        )

    def jail_rate(self, wanted_level, rounds=4000):
        from game.crime.service import commit_crime

        rng = random.Random(1234)
        jailed = 0
        for _ in range(rounds):
            player = self.player(wanted_level)
            result = commit_crime(
                player,
                CRIMES_BY_KEY["camden_market_stall"],
                rng=rng,
            )
            if getattr(result, "consequence", None) == "jail":
                jailed += 1
        return jailed / rounds

    def test_a_wanted_player_is_jailed_more_often(self):
        cold = self.jail_rate(0)
        hot = self.jail_rate(MAX_WANTED_LEVEL)

        self.assertGreater(
            hot,
            cold,
            f"heat changed nothing: {cold:.3f} cold, {hot:.3f} hot",
        )

    def test_the_difference_stays_gentle(self):
        cold = self.jail_rate(0)
        hot = self.jail_rate(MAX_WANTED_LEVEL)

        # Half again as likely, not several times.
        self.assertLess(hot, cold * 2)


if __name__ == "__main__":
    unittest.main()
