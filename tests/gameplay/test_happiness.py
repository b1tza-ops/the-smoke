import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from game.crime import commit_crime, get_crime
from game.gym import calculate_training_gain, train
from game.player.happiness import (
    crime_success_penalty,
    happiness_ratio,
    training_multiplier,
)
from game.player.status import (
    JAIL_HAPPINESS_LOSS,
    HOSPITAL_HAPPINESS_LOSS,
    send_to_hospital,
    send_to_jail,
)


class HappinessHelperTests(unittest.TestCase):
    def test_full_happiness_has_no_effect(self):
        player = SimpleNamespace(happiness=100, max_happiness=100)

        self.assertEqual(happiness_ratio(player), 1.0)
        self.assertEqual(training_multiplier(player), 1.0)
        self.assertEqual(crime_success_penalty(player), 0)

    def test_empty_happiness_applies_maximum_penalty(self):
        player = SimpleNamespace(happiness=0, max_happiness=100)

        self.assertEqual(happiness_ratio(player), 0.0)
        self.assertEqual(training_multiplier(player), 0.5)
        self.assertEqual(crime_success_penalty(player), 10)

    def test_half_happiness_applies_half_effect(self):
        player = SimpleNamespace(happiness=50, max_happiness=100)

        self.assertEqual(training_multiplier(player), 0.75)
        self.assertEqual(crime_success_penalty(player), 5)

    def test_missing_happiness_attribute_is_treated_as_full(self):
        player = SimpleNamespace(level=1)

        self.assertIsNone(happiness_ratio(player))
        self.assertEqual(training_multiplier(player), 1.0)
        self.assertEqual(crime_success_penalty(player), 0)

    def test_none_player_is_treated_as_full(self):
        self.assertEqual(training_multiplier(None), 1.0)
        self.assertEqual(crime_success_penalty(None), 0)


class HappinessStatusIntegrationTests(unittest.TestCase):
    def test_jail_reduces_happiness_when_present(self):
        player = SimpleNamespace(jail_until=None, happiness=100)

        send_to_jail(player, 600)

        self.assertEqual(player.happiness, 100 - JAIL_HAPPINESS_LOSS)

    def test_hospital_reduces_happiness_when_present(self):
        player = SimpleNamespace(hospital_until=None, happiness=100)

        send_to_hospital(player, 600)

        self.assertEqual(
            player.happiness,
            100 - HOSPITAL_HAPPINESS_LOSS,
        )

    def test_happiness_never_drops_below_zero(self):
        player = SimpleNamespace(jail_until=None, happiness=2)

        send_to_jail(player, 600)

        self.assertEqual(player.happiness, 0)

    def test_status_helpers_tolerate_missing_happiness(self):
        player = SimpleNamespace(jail_until=None, hospital_until=None)

        send_to_jail(player, 600)
        send_to_hospital(player, 600)

        self.assertFalse(hasattr(player, "happiness"))


class HappinessGymIntegrationTests(unittest.TestCase):
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
            "current_gym_key": "camden_community",
            "unlocked_gyms": {"camden_community"},
            "travel_destination": None,
            "travel_until": None,
            "wanted_level": 0,
            "last_wanted_update": None,
            "jail_until": None,
            "hospital_until": None,
            "last_energy_update": None,
            "happiness": 100,
            "max_happiness": 100,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_reduced_happiness_softens_training_gain(self):
        player = self.make_player(happiness=0)

        trained = train(player, "strength", energy=10)

        self.assertTrue(trained)
        self.assertEqual(player.strength, 11.0)

    def test_full_happiness_matches_unboosted_gain(self):
        player = self.make_player()

        trained = train(player, "strength", energy=10)

        self.assertTrue(trained)
        self.assertEqual(player.strength, 12.0)

    def test_calculate_training_gain_accepts_optional_player(self):
        happy_player = self.make_player()
        sad_player = self.make_player(happiness=0)

        self.assertEqual(
            calculate_training_gain(
                "camden_community", "strength", 10, player=happy_player,
            ),
            2.0,
        )
        self.assertEqual(
            calculate_training_gain(
                "camden_community", "strength", 10, player=sad_player,
            ),
            1.0,
        )


class HappinessCrimeIntegrationTests(unittest.TestCase):
    def make_player(self, happiness=100, max_happiness=100):
        return SimpleNamespace(
            nerve=20,
            money=100,
            health=100,
            xp=0,
            level=1,
            crime_progress={},
            district_reputation={},
            wanted_level=0,
            current_district="soho",
            travel_destination=None,
            travel_until=None,
            last_wanted_update=None,
            jail_until=None,
            hospital_until=None,
            happiness=happiness,
            max_happiness=max_happiness,
        )

    def test_low_happiness_can_turn_a_success_into_a_failure(self):
        crime = get_crime("soho_pickpocket")
        rng = Mock()
        rng.randint.side_effect = [60, 1, 5]

        player = self.make_player(happiness=0)
        result = commit_crime(player, crime, rng=rng)

        self.assertFalse(result.success)

    def test_full_happiness_keeps_the_unboosted_chance(self):
        crime = get_crime("soho_pickpocket")
        rng = Mock()
        rng.randint.side_effect = [60, 1]

        player = self.make_player(happiness=100)
        result = commit_crime(player, crime, rng=rng)

        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
