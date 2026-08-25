from types import SimpleNamespace
import unittest

from game.gym import (
    DEFAULT_GYM_KEY,
    GYMS,
    GymLevelError,
    GymLocationError,
    GymLockedError,
    GymMembershipFundsError,
    calculate_training_gain,
    select_gym,
    train,
    unlock_gym,
)


class DistrictGymTests(unittest.TestCase):
    def make_player(self, **overrides):
        values = {
            "level": 1,
            "money": 500,
            "energy": 100,
            "strength": 10,
            "defence": 10,
            "speed": 10,
            "dexterity": 10,
            "current_district": "camden",
            "current_gym_key": DEFAULT_GYM_KEY,
            "unlocked_gyms": {DEFAULT_GYM_KEY},
            "travel_destination": None,
            "travel_until": None,
            "wanted_level": 0,
            "last_wanted_update": None,
            "jail_until": None,
            "hospital_until": None,
            "last_energy_update": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_eight_progressive_gyms_cover_early_districts(self):
        self.assertEqual(len(GYMS), 8)
        self.assertEqual(
            {gym.district for gym in GYMS},
            {"camden", "brixton", "soho"},
        )

    def test_training_gain_uses_selected_gym_multiplier(self):
        """Compared one train at a time, so the rates are exact.

        Across a batch the stat itself rises, which lifts the later
        trains and leaves the totals just off a round number.
        """
        camden_gain = calculate_training_gain(
            "camden_community",
            "speed",
            5,
        )
        brixton_gain = calculate_training_gain(
            "brixton_performance",
            "speed",
            10,
        )

        # 0.2 a point of energy at x1.0, and x1.6 at Brixton.
        self.assertEqual(camden_gain, 1.0)
        self.assertEqual(brixton_gain, 3.2)

    def test_player_can_spend_one_hundred_energy(self):
        player = self.make_player()

        trained = train(
            player,
            "strength",
            energy=100,
        )

        self.assertTrue(trained)
        self.assertEqual(player.energy, 0)
        self.assertEqual(player.strength, 30.2)

    def test_training_energy_must_be_a_multiple_of_the_gyms_cost(self):
        """Valid energy now depends on the gym, not a global 10.

        Camden is lightweight, so 15 is three legal trains there while
        10 buys nothing at a heavyweight gym.
        """
        player = self.make_player()

        for invalid_energy in (0, -10, 12, True, 10.5):
            with self.subTest(energy=invalid_energy):
                with self.assertRaises(ValueError):
                    train(
                        player,
                        "strength",
                        energy=invalid_energy,
                    )

        elite = self.make_player(
            level=4,
            money=20_000,
            current_district="soho",
            unlocked_gyms={"soho_london_elite"},
            current_gym_key="soho_london_elite",
        )

        with self.assertRaises(ValueError):
            train(
                elite,
                "strength",
                energy=10,
                gym_key="soho_london_elite",
            )

    def test_lightweight_gym_accepts_its_own_smaller_multiples(self):
        player = self.make_player()

        trained = train(player, "strength", energy=15)

        self.assertTrue(trained)
        self.assertEqual(trained.trains, 3)
        self.assertEqual(player.energy, 85)

    def test_brixton_membership_cost_and_access_persist_in_player(self):
        player = self.make_player(
            level=2,
            money=1_000,
            current_district="brixton",
        )

        result = unlock_gym(
            player,
            "brixton_performance",
        )
        select_gym(
            player,
            "brixton_performance",
        )

        self.assertEqual(result.membership_cost, 500)
        self.assertEqual(player.money, 500)
        self.assertIn(
            "brixton_performance",
            player.unlocked_gyms,
        )
        self.assertEqual(
            player.current_gym_key,
            "brixton_performance",
        )

    def test_locked_gym_cannot_be_selected(self):
        player = self.make_player(
            level=2,
            current_district="brixton",
        )

        with self.assertRaises(GymLockedError):
            select_gym(
                player,
                "brixton_performance",
            )

    def test_membership_requires_level_cash_and_location(self):
        low_level = self.make_player(
            current_district="brixton",
            money=1_000,
        )
        with self.assertRaises(GymLevelError):
            unlock_gym(
                low_level,
                "brixton_performance",
            )

        low_cash = self.make_player(
            level=2,
            current_district="brixton",
            money=499,
        )
        with self.assertRaises(
            GymMembershipFundsError
        ):
            unlock_gym(
                low_cash,
                "brixton_performance",
            )

        wrong_district = self.make_player(
            level=2,
            money=1_000,
        )
        with self.assertRaises(GymLocationError):
            unlock_gym(
                wrong_district,
                "brixton_performance",
            )

    def test_specialised_gym_changes_actual_training_gain(self):
        player = self.make_player(
            level=2,
            money=1_000,
            current_district="brixton",
        )
        unlock_gym(
            player,
            "brixton_performance",
        )
        select_gym(
            player,
            "brixton_performance",
        )

        trained = train(
            player,
            "strength",
            energy=20,
        )

        self.assertTrue(trained)
        self.assertEqual(player.energy, 80)
        self.assertEqual(player.strength, 16.44)


if __name__ == "__main__":
    unittest.main()
