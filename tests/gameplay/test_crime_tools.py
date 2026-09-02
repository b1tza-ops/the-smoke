"""Five items that did nothing, and now do.

A lockpick, bolt cutters, a glass cutter, duct tape and a burner phone
have sat in the catalogue since the loot system shipped. They drop from
crimes and they have a resale price, and holding one had never once
changed an outcome. The fastest thing a player could do with any of them
was walk to the fence.

Now each suits particular jobs, which gives loot a reason to stay in a
pocket. The rules are deliberately small: a modest bonus, a cap so the
answer is not "carry everything", nothing ever required, and a chance to
leave kit behind when a job goes wrong so the demand does not end after
one shopping trip.
"""

import random
import unittest
from types import SimpleNamespace

from game.crime import CRIMES, CRIMES_BY_KEY
from game.crime.progression import crime_progression_for
from game.crime.service import commit_crime
from game.crime.tools import (
    CRIME_TOOLS,
    MAXIMUM_TOOLS_PER_JOB,
    TOOL_LOSS_CHANCE_ON_FAILURE,
    TOOL_SUCCESS_BONUS,
    TOOLS,
    TOOLS_BY_KEY,
    tool_bonus,
    tool_left_behind,
    tools_for,
    usable_tools,
)


def thief(inventory=None, **changes):
    values = dict(
        inventory=dict(inventory or {}),
        crime_progress={},
        district_reputation={},
        current_district="brixton",
        level=20, money=0, energy=100, nerve=100,
        happiness=100, max_happiness=100,
        health=100, max_health=100, xp=0, wanted_level=0,
        jail_until=None, hospital_until=None,
        travel_destination=None, travel_until=None,
        last_wanted_update=None, last_happiness_update=None,
        last_energy_update=None, last_nerve_update=None,
        max_energy=150, max_nerve=100, residence_key="tent",
    )
    values.update(changes)
    return SimpleNamespace(**values)


class ToolCatalogueTests(unittest.TestCase):
    def test_every_tool_is_wanted_somewhere(self):
        """A tool nothing asks for is the problem this fixes."""
        wanted = {
            key for keys in CRIME_TOOLS.values() for key in keys
        }

        for tool in TOOLS:
            with self.subTest(tool=tool.key):
                self.assertIn(tool.key, wanted)

    def test_every_crime_has_an_entry(self):
        self.assertEqual(
            set(CRIME_TOOLS),
            {crime.key for crime in CRIMES},
            "a crime with no entry silently ignores kit",
        )

    def test_the_starter_crime_needs_nothing(self):
        # A new player has an empty inventory and must not be behind
        # for it.
        self.assertEqual(tools_for("camden_shoplift"), ())

    def test_every_named_tool_exists_in_the_catalogue(self):
        from game.inventory import ITEMS_BY_KEY

        for tool in TOOLS:
            with self.subTest(tool=tool.key):
                self.assertIn(tool.key, ITEMS_BY_KEY)


class BonusTests(unittest.TestCase):
    def test_carrying_nothing_is_worth_nothing(self):
        self.assertEqual(tool_bonus({}, "brixton_warehouse"), 0)
        self.assertEqual(tool_bonus(None, "brixton_warehouse"), 0)

    def test_the_right_tool_helps(self):
        self.assertEqual(
            tool_bonus({"bolt_cutters": 1}, "brixton_warehouse"),
            TOOL_SUCCESS_BONUS,
        )

    def test_the_wrong_tool_does_not(self):
        self.assertEqual(
            tool_bonus({"burner_phone": 1}, "brixton_warehouse"), 0
        )

    def test_a_full_toolbox_is_worth_no_more_than_two(self):
        """Otherwise the answer to every job is 'carry everything'."""
        everything = {tool.key: 1 for tool in TOOLS}

        self.assertEqual(
            tool_bonus(everything, "brixton_warehouse"),
            TOOL_SUCCESS_BONUS * MAXIMUM_TOOLS_PER_JOB,
        )

    def test_an_empty_stack_does_not_count(self):
        self.assertEqual(
            tool_bonus({"bolt_cutters": 0}, "brixton_warehouse"), 0
        )

    def test_it_stays_smaller_than_what_you_earn(self):
        # Mastery tops out at 8 points and is earned by playing; kit is
        # bought. Kit must not dwarf it.
        from game.crime.progression import MASTERY_TIERS

        best_mastery = max(tier.success_bonus for tier in MASTERY_TIERS)

        self.assertLessEqual(
            TOOL_SUCCESS_BONUS * MAXIMUM_TOOLS_PER_JOB,
            best_mastery,
        )


class OddsTests(unittest.TestCase):
    def test_the_bonus_reaches_the_stated_chance(self):
        crime = CRIMES_BY_KEY["brixton_warehouse"]

        bare = crime_progression_for(thief(), crime)
        kitted = crime_progression_for(
            thief({"bolt_cutters": 1, "lockpick": 1}), crime
        )

        self.assertEqual(
            kitted.effective_success_chance,
            bare.effective_success_chance
            + TOOL_SUCCESS_BONUS * MAXIMUM_TOOLS_PER_JOB,
        )

    def test_the_page_can_say_what_is_being_carried(self):
        kitted = crime_progression_for(
            thief({"bolt_cutters": 1}), CRIMES_BY_KEY["brixton_warehouse"]
        )

        self.assertEqual(
            [tool.key for tool in kitted.tools], ["bolt_cutters"]
        )
        self.assertEqual(kitted.tool_bonus, TOOL_SUCCESS_BONUS)

    def test_kit_never_pushes_past_the_ceiling(self):
        from game.crime.progression import MAX_SUCCESS_CHANCE

        for crime in CRIMES:
            with self.subTest(crime=crime.key):
                kitted = crime_progression_for(
                    thief({tool.key: 1 for tool in TOOLS}), crime
                )
                self.assertLessEqual(
                    kitted.effective_success_chance, MAX_SUCCESS_CHANCE
                )


class LosingKitTests(unittest.TestCase):
    def test_nothing_is_lost_when_nothing_suitable_is_carried(self):
        self.assertIsNone(
            tool_left_behind({}, "brixton_warehouse", random.Random(1))
        )

    def test_at_most_one_tool_goes_at_a_time(self):
        """Losing the whole kit to one bad roll would feel like a bug."""
        carried = {"bolt_cutters": 1, "lockpick": 1}

        for seed in range(40):
            dropped = tool_left_behind(
                carried, "brixton_warehouse", random.Random(seed)
            )
            with self.subTest(seed=seed):
                self.assertIn(dropped, (None, *TOOLS_BY_KEY.values()))

    def test_it_happens_about_as_often_as_advertised(self):
        rng = random.Random(5)
        dropped = sum(
            1 for _ in range(4000)
            if tool_left_behind(
                {"bolt_cutters": 1}, "brixton_warehouse", rng
            )
        )

        self.assertAlmostEqual(
            dropped / 4000 * 100, TOOL_LOSS_CHANCE_ON_FAILURE, delta=3
        )


class ThroughACrimeTests(unittest.TestCase):
    def run_jobs(self, inventory, rounds=2000, seed=11):
        rng = random.Random(seed)
        crime = CRIMES_BY_KEY["brixton_warehouse"]
        failures = lost = successes = lost_on_success = 0

        for _ in range(rounds):
            player = thief(inventory)
            result = commit_crime(player, crime, rng=rng)
            held = sum(
                player.inventory.get(key, 0) for key in inventory
            )
            missing = held < sum(inventory.values())
            if result.success:
                successes += 1
                lost_on_success += missing
            else:
                failures += 1
                lost += missing

        return failures, lost, successes, lost_on_success

    def test_a_successful_job_never_costs_you_kit(self):
        _, _, successes, lost = self.run_jobs({"bolt_cutters": 1})

        self.assertGreater(successes, 0)
        self.assertEqual(lost, 0)

    def test_a_botched_job_sometimes_does(self):
        failures, lost, _, _ = self.run_jobs({"bolt_cutters": 1})

        self.assertGreater(failures, 0)
        self.assertAlmostEqual(
            lost / failures * 100, TOOL_LOSS_CHANCE_ON_FAILURE, delta=4
        )

    def test_carrying_kit_really_does_win_more_jobs(self):
        """The whole point, measured end to end."""
        def wins(inventory):
            rng = random.Random(99)
            crime = CRIMES_BY_KEY["brixton_warehouse"]
            return sum(
                1 for _ in range(3000)
                if commit_crime(
                    thief(inventory), crime, rng=rng
                ).success
            )

        self.assertGreater(
            wins({"bolt_cutters": 1, "lockpick": 1}),
            wins({}),
        )


if __name__ == "__main__":
    unittest.main()
