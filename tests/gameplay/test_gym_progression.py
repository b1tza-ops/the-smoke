import unittest

from game.gym import (
    GAIN_BAR_SEGMENTS,
    GAIN_SCALE_MAX,
    GYMS,
    GymStatUnavailableError,
    calculate_training_gain,
)
from game.world.districts import DISTRICTS


class GymProgressionTests(unittest.TestCase):
    def test_the_roster_runs_from_free_to_the_top_of_london(self):
        # The price of the top gym is deliberately not pinned here.
        # What this test is about is the shape of the roster: fourteen
        # gyms, the first free, the last the dearest in London. What
        # that costs is a balance decision, held to a curve in
        # tests/gameplay/test_gym_pricing.py instead.
        self.assertEqual(len(GYMS), 14)
        self.assertEqual(GYMS[0].membership_cost, 0)
        self.assertEqual(
            GYMS[-1].membership_cost,
            max(gym.membership_cost for gym in GYMS),
        )

    def test_membership_cost_level_and_gains_all_rise_together(self):
        costs = [gym.membership_cost for gym in GYMS]
        levels = [gym.required_level for gym in GYMS]
        # Averaged over the stats each gym actually trains: a
        # specialist can beat the gym above it on its one strong stat
        # without being the better gym overall.
        average = [
            sum(
                gym.multiplier_for(stat)
                for stat in ("strength", "defence", "speed", "dexterity")
                if gym.trains(stat)
            )
            / sum(
                1
                for stat in ("strength", "defence", "speed", "dexterity")
                if gym.trains(stat)
            )
            for gym in GYMS
        ]

        self.assertEqual(costs, sorted(costs))
        self.assertEqual(levels, sorted(levels))
        self.assertEqual(average, sorted(average))

    def test_the_cheap_end_of_the_roster_stays_lightweight(self):
        """Weight class follows price, not district, as in Torn.

        A player spends a long run of gyms on 5 energy a train before
        the commitments get bigger.
        """
        lightweight = [
            gym for gym in GYMS if gym.weight_class == "lightweight"
        ]

        self.assertEqual(len(lightweight), 6)
        self.assertEqual(lightweight, list(GYMS[:6]))

    def test_gains_progress_from_starter_to_elite(self):
        """The elite gym is worth twice the starter, per energy.

        One train at each, because the two charge different amounts per
        train and a longer batch lifts itself as the stat rises.
        """
        camden = calculate_training_gain(
            "camden_community",
            "strength",
            5,
        )
        elite = calculate_training_gain(
            "soho_london_elite",
            "strength",
            10,
        )

        self.assertEqual(camden, 1.0)
        self.assertEqual(elite, 4.0)
        self.assertEqual(elite / 10, camden / 5 * 2)

    def test_specialist_gym_rejects_unavailable_stat(self):
        with self.assertRaises(GymStatUnavailableError):
            calculate_training_gain(
                "brixton_performance",
                "dexterity",
                10,
            )

    def test_every_district_has_somewhere_to_train(self):
        self.assertEqual(
            {gym.district for gym in GYMS},
            {district.key for district in DISTRICTS},
        )

    def test_the_gain_scale_leaves_room_above_the_best_gym(self):
        """The top of the roster must not fill the bar.

        A full bar reads as finished, and the scale then has to be
        rewritten the moment a better gym is added.
        """
        best = max(
            gym.multiplier_for(stat)
            for gym in GYMS
            for stat in ("strength", "defence", "speed", "dexterity")
        )

        self.assertLess(best, GAIN_SCALE_MAX)
        self.assertGreater(best / GAIN_SCALE_MAX, 0.5)

    def test_the_free_gym_still_registers_on_the_bar(self):
        # A starter gym that draws as empty looks broken.
        filled = round(
            GYMS[0].multiplier_for("strength")
            / GAIN_SCALE_MAX
            * GAIN_BAR_SEGMENTS
        )

        self.assertGreaterEqual(filled, 1)

    def test_east_london_carries_the_top_of_the_roster(self):
        top_five = GYMS[-5:]

        self.assertEqual(
            {gym.district for gym in top_five},
            {"shoreditch", "hackney"},
        )
        for gym in top_five:
            with self.subTest(gym=gym.key):
                self.assertGreaterEqual(gym.required_level, 5)


if __name__ == "__main__":
    unittest.main()
