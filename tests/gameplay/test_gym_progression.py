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

        Compared at equal *energy* rather than equal trains: the two
        charge different amounts per train now, so per-train figures
        are no longer comparable between them.
        """
        self.assertEqual(
            calculate_training_gain(
                "camden_community",
                "strength",
                100,
            ),
            20.0,
        )
        self.assertEqual(
            calculate_training_gain(
                "soho_london_elite",
                "strength",
                100,
            ),
            40.0,
        )

    def test_specialist_gym_rejects_unavailable_stat(self):
        with self.assertRaises(GymStatUnavailableError):
            calculate_training_gain(
                "brixton_performance",
                "dexterity",
                10,
            )


if __name__ == "__main__":
    unittest.main()
