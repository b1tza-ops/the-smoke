import unittest

from game.gym import (
    GYMS,
    GymStatUnavailableError,
    calculate_training_gain,
)


class GymProgressionTests(unittest.TestCase):
    def test_london_progression_has_eight_gyms(self):
        self.assertEqual(len(GYMS), 8)
        self.assertEqual(GYMS[0].membership_cost, 0)
        self.assertEqual(GYMS[-1].membership_cost, 10_000)

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
            25,
        )

        self.assertEqual(camden, 1.0)
        self.assertEqual(elite, 10.0)
        self.assertEqual(elite / 25, camden / 5 * 2)

    def test_specialist_gym_rejects_unavailable_stat(self):
        with self.assertRaises(GymStatUnavailableError):
            calculate_training_gain(
                "brixton_performance",
                "dexterity",
                10,
            )


if __name__ == "__main__":
    unittest.main()
