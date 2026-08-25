from types import SimpleNamespace
import unittest

from game.operations import (
    CAMPAIGN,
    OPERATIONS_BY_KEY,
    approach_shortfalls,
    campaign_status,
    can_attempt,
    get_operation,
    next_operation,
)


DISTRICT_NAMES = {
    "camden": "Camden",
    "brixton": "Brixton",
    "soho": "Soho",
}


class CampaignDefinitionTests(unittest.TestCase):
    def test_every_operation_has_three_distinct_approaches(self):
        for operation in CAMPAIGN:
            with self.subTest(operation=operation.key):
                keys = [
                    approach.key
                    for approach in operation.approaches
                ]
                self.assertEqual(len(keys), 3)
                self.assertEqual(len(set(keys)), 3)

    def test_every_operation_offers_all_three_stats(self):
        for operation in CAMPAIGN:
            with self.subTest(operation=operation.key):
                self.assertEqual(
                    {
                        approach.stat
                        for approach in operation.approaches
                    },
                    {"strength", "speed", "dexterity"},
                )

    def test_operation_keys_are_unique(self):
        self.assertEqual(len(OPERATIONS_BY_KEY), len(CAMPAIGN))

    def test_every_operation_is_in_a_real_district(self):
        for operation in CAMPAIGN:
            with self.subTest(operation=operation.key):
                self.assertIn(operation.district, DISTRICT_NAMES)

    def test_level_requirements_only_ever_rise(self):
        levels = [
            operation.required_level
            for operation in CAMPAIGN
        ]

        self.assertEqual(levels, sorted(levels))

    def test_the_first_operation_keeps_its_prologue_approach_keys(self):
        # Completed accounts store these, so they cannot be renamed.
        self.assertEqual(
            {
                approach.key
                for approach in CAMPAIGN[0].approaches
            },
            {
                "talk_your_way_in",
                "slip_through_back",
                "force_the_door",
            },
        )

    def test_only_the_finale_clears_the_debt(self):
        self.assertTrue(CAMPAIGN[-1].clears_debt)
        self.assertFalse(
            any(operation.clears_debt for operation in CAMPAIGN[:-1])
        )

    def test_the_debt_always_survives_to_the_finale(self):
        # Otherwise the last operation, whose whole point is settling
        # up, would have nothing left to settle.
        best_case = sum(
            max(
                approach.paydown
                for approach in operation.approaches
            )
            for operation in CAMPAIGN[:-1]
        )

        self.assertLess(best_case, 2000)

    def test_rewards_grow_across_the_campaign(self):
        payouts = [
            min(approach.cash for approach in operation.approaches)
            for operation in CAMPAIGN
        ]

        self.assertEqual(payouts, sorted(payouts))
        self.assertEqual(len(set(payouts)), len(payouts))

    def test_no_approach_costs_more_nerve_than_a_player_can_hold(self):
        # 20 base, plus the 5 a street hustler starts with.
        for operation in CAMPAIGN:
            for approach in operation.approaches:
                with self.subTest(approach=approach.key):
                    self.assertLessEqual(approach.nerve, 20)

    def test_no_approach_costs_more_energy_than_a_full_bar(self):
        for operation in CAMPAIGN:
            for approach in operation.approaches:
                with self.subTest(approach=approach.key):
                    self.assertLessEqual(approach.energy, 150)

    def test_an_unknown_operation_resolves_to_nothing(self):
        self.assertIsNone(get_operation("not_an_operation"))
        self.assertIsNone(CAMPAIGN[0].approach_for("not_an_approach"))


class CampaignStatusTests(unittest.TestCase):
    def make_player(self, **overrides):
        values = {
            "level": 1,
            "current_district": "camden",
            "energy": 150,
            "nerve": 20,
            "strength": 10,
            "speed": 10,
            "dexterity": 10,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def status_for(self, key, player, records):
        for status in campaign_status(
            player,
            records,
            district_names=DISTRICT_NAMES,
        ):
            if status.operation.key == key:
                return status

        raise AssertionError(f"{key} is not in the campaign")

    def test_a_fresh_player_sees_only_the_first_operation_open(self):
        statuses = campaign_status(
            self.make_player(),
            {},
            district_names=DISTRICT_NAMES,
        )

        self.assertEqual(statuses[0].stage, "available")
        self.assertTrue(statuses[0].is_open)
        self.assertTrue(
            all(status.stage == "locked" for status in statuses[1:])
        )

    def test_the_previous_operation_gates_the_next(self):
        status = self.status_for(
            "soho_favour",
            self.make_player(level=30, current_district="soho"),
            {},
        )

        self.assertEqual(
            status.lock_reason,
            "Complete The Camden Collection first",
        )

    def test_level_gates_before_district(self):
        # A player who is short on both should be told to level up
        # first, since travelling would not help them.
        status = self.status_for(
            "soho_favour",
            self.make_player(level=1, current_district="camden"),
            {"camden_collection": {"stage": "completed"}},
        )

        self.assertEqual(status.lock_reason, "Reach level 3")

    def test_district_gates_once_the_level_is_reached(self):
        status = self.status_for(
            "soho_favour",
            self.make_player(level=3, current_district="camden"),
            {"camden_collection": {"stage": "completed"}},
        )

        self.assertEqual(status.lock_reason, "Travel to Soho")

    def test_a_running_operation_keeps_the_rest_shut(self):
        # The chain is what limits a player to one at a time: the
        # running operation is not complete, so nothing behind it opens.
        records = {
            "camden_collection": {"stage": "completed"},
            "soho_favour": {
                "stage": "active",
                "approach": "roof_and_skylight",
                "remaining_seconds": 120,
            },
        }
        player = self.make_player(level=30, current_district="brixton")
        statuses = campaign_status(
            player,
            records,
            district_names=DISTRICT_NAMES,
        )

        active = self.status_for("soho_favour", player, records)
        self.assertEqual(active.stage, "active")
        self.assertEqual(active.remaining_seconds, 120)
        self.assertEqual(
            statuses[2].lock_reason,
            "Complete A Favour in Soho first",
        )

    def test_a_completed_operation_reports_its_own_record(self):
        status = self.status_for(
            "camden_collection",
            self.make_player(),
            {
                "camden_collection": {
                    "stage": "completed",
                    "approach": "force_the_door",
                    "outcome_text": "The door gave way.",
                    "paydown": 550,
                },
            },
        )

        self.assertEqual(status.stage, "completed")
        self.assertEqual(status.paydown, 550)
        self.assertEqual(status.outcome_text, "The door gave way.")

    def test_a_retired_approach_key_still_reads_back(self):
        # V1 accounts stored choices the campaign no longer defines.
        status = self.status_for(
            "camden_collection",
            self.make_player(),
            {
                "camden_collection": {
                    "stage": "completed",
                    "approach": "deliver_package",
                    "outcome_text": "The package was warm.",
                    "paydown": 350,
                },
            },
        )

        self.assertEqual(status.stage, "completed")
        self.assertEqual(status.outcome_text, "The package was warm.")
        self.assertIsNone(
            status.operation.approach_for(status.approach_key)
        )

    def test_next_operation_leads_with_the_active_one(self):
        records = {
            "camden_collection": {"stage": "completed"},
            "soho_favour": {"stage": "active", "approach": "walk_in_loud"},
        }
        statuses = campaign_status(
            self.make_player(level=30, current_district="soho"),
            records,
            district_names=DISTRICT_NAMES,
        )

        self.assertEqual(
            next_operation(statuses).operation.key,
            "soho_favour",
        )

    def test_next_operation_is_nothing_once_the_campaign_is_done(self):
        records = {
            operation.key: {"stage": "completed"}
            for operation in CAMPAIGN
        }
        statuses = campaign_status(
            self.make_player(),
            records,
            district_names=DISTRICT_NAMES,
        )

        self.assertIsNone(next_operation(statuses))


class ApproachRequirementTests(unittest.TestCase):
    def setUp(self):
        self.approach = CAMPAIGN[0].approach_for("force_the_door")

    def make_player(self, **overrides):
        values = {
            "strength": 10,
            "speed": 10,
            "dexterity": 10,
            "energy": 150,
            "nerve": 20,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_a_ready_player_has_no_shortfalls(self):
        self.assertEqual(
            approach_shortfalls(self.make_player(), self.approach),
            [],
        )
        self.assertTrue(can_attempt(self.make_player(), self.approach))

    def test_every_missing_requirement_is_named(self):
        shortfalls = approach_shortfalls(
            self.make_player(strength=4, energy=2, nerve=1),
            self.approach,
        )

        self.assertEqual(
            shortfalls,
            ["10 strength", "12 energy", "7 nerve"],
        )
        self.assertFalse(
            can_attempt(
                self.make_player(strength=4),
                self.approach,
            )
        )


if __name__ == "__main__":
    unittest.main()
