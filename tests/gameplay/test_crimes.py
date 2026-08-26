import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from datetime import datetime, timezone
from contextlib import redirect_stdout
from io import StringIO
from game.crime import (
    CRIMES,
    MAX_REPUTATION_BONUS_PERCENT,
    MAX_SUCCESS_CHANCE,
    CrimeResult,
    commit_crime,
    crime_progression_for,
    display_crime_result,
    get_crime,
)
from game.world.districts import DISTRICTS
class CrimeDefinitionTests(unittest.TestCase):
    def test_every_district_has_crimes_of_its_own(self):
        # Derived from the district catalogue, so a new district cannot
        # ship as an empty room.
        districts = {crime.district for crime in CRIMES}

        self.assertEqual(
            districts,
            {district.name for district in DISTRICTS},
        )
        self.assertEqual(len({crime.key for crime in CRIMES}), len(CRIMES))


class CrimeProgressionTests(unittest.TestCase):
    def make_player(self, crime_xp=0, reputation=0):
        return SimpleNamespace(
            crime_progress={
                "soho_pickpocket": {
                    "xp": crime_xp,
                    "attempts": 0,
                    "successes": 0,
                },
            },
            district_reputation={"Soho": reputation},
        )

    def test_mastery_thresholds_raise_success_in_small_steps(self):
        crime = get_crime("soho_pickpocket")

        expected = (
            (0, "Newcomer", 0),
            (100, "Practised", 2),
            (300, "Skilled", 4),
            (750, "Expert", 6),
            (1500, "Master", 8),
        )

        for crime_xp, name, bonus in expected:
            with self.subTest(crime_xp=crime_xp):
                progression = crime_progression_for(
                    self.make_player(crime_xp=crime_xp),
                    crime,
                )
                self.assertEqual(progression.mastery_name, name)
                self.assertEqual(progression.mastery_bonus, bonus)
                self.assertEqual(
                    progression.effective_success_chance,
                    crime.success_chance + bonus,
                )

    def test_success_chance_never_exceeds_cap(self):
        crime = replace(
            get_crime("camden_shoplift"),
            success_chance=99,
        )
        player = SimpleNamespace(
            crime_progress={
                crime.key: {"xp": 999999},
            },
            district_reputation={},
        )

        progression = crime_progression_for(player, crime)

        self.assertLessEqual(
            progression.effective_success_chance,
            MAX_SUCCESS_CHANCE,
        )

    def test_reputation_bonus_is_gradual_and_capped(self):
        crime = get_crime("soho_pickpocket")
        progression = crime_progression_for(
            self.make_player(reputation=250),
            crime,
        )
        capped = crime_progression_for(
            self.make_player(reputation=999999),
            crime,
        )

        self.assertEqual(progression.reputation_bonus_percent, 10)
        self.assertEqual(progression.min_reward, 55)
        self.assertEqual(progression.max_reward, 165)
        self.assertEqual(
            capped.reputation_bonus_percent,
            MAX_REPUTATION_BONUS_PERCENT,
        )

    def test_happiness_penalty_applies_after_mastery(self):
        crime = get_crime("soho_pickpocket")
        progression = crime_progression_for(
            self.make_player(crime_xp=300),
            crime,
            happiness_penalty=12,
        )

        self.assertEqual(
            progression.effective_success_chance,
            crime.success_chance + 4 - 12,
        )


class CrimeEngineTests(unittest.TestCase):
    def make_player(self, nerve=20,current_district ="camden"):
        return SimpleNamespace(
            nerve=nerve,
            money=100,
            health=100,
            xp=0,
            level=1,
            crime_progress={},
            district_reputation={},
            wanted_level=0,
            current_district=current_district,
            travel_destination = None,
            travel_until = None,
            last_wanted_update=None,
            jail_until=None,
            hospital_until=None,
        )

    def test_success_returns_structured_result_and_progress(self):
        player = self.make_player(
            current_district="soho"
        )
        crime = get_crime("soho_pickpocket")
        rng = Mock()
        rng.randint.side_effect = [1, 75, 100]

        result = commit_crime(player, crime, rng=rng)

        self.assertIsInstance(result, CrimeResult)
        self.assertTrue(result.attempted)
        self.assertTrue(result.success)
        self.assertEqual(result.cash_reward, 75)
        self.assertEqual(player.money, 175)
        self.assertEqual(player.xp, crime.xp_reward)
        self.assertEqual(player.nerve, 16)
        self.assertEqual(
            player.crime_progress[crime.key],
            {
                "xp": crime.crime_xp_reward,
                "attempts": 1,
                "successes": 1,
            },
        )

        self.assertEqual(
            player.wanted_level,
            crime.wanted_gain,
        )
        self.assertEqual(
            player.district_reputation["Soho"],
            crime.reputation_reward,
        )

    def test_failure_grants_no_cash_xp_or_reputation(self):
        player = self.make_player(
        current_district="brixton"
        )
        crime = get_crime("brixton_warehouse")
        rng = Mock()
        rng.randint.side_effect = [100, 100, 8]

        result = commit_crime(player, crime, rng=rng)

        self.assertTrue(result.attempted)
        self.assertFalse(result.success)
        self.assertEqual(result.cash_reward, 0)
        self.assertEqual(player.money, 100)
        self.assertEqual(player.xp, 0)
        self.assertEqual(player.district_reputation, {})
        self.assertEqual(
            player.crime_progress[crime.key],
            {"xp": 0, "attempts": 1, "successes": 0},
        )
        self.assertEqual(
            player.wanted_level,
            crime.wanted_gain,
        )

    def test_existing_mastery_and_reputation_change_the_attempt(self):
        player = self.make_player(current_district="soho")
        crime = get_crime("soho_pickpocket")
        player.crime_progress[crime.key] = {
            "xp": 300,
            "attempts": 5,
            "successes": 4,
        }
        player.district_reputation[crime.district] = 250
        rng = Mock()
        rng.randint.side_effect = [69, 75, 100]

        result = commit_crime(player, crime, rng=rng)

        self.assertTrue(result.success)
        self.assertEqual(result.effective_success_chance, 69)
        self.assertEqual(result.mastery_bonus, 4)
        self.assertEqual(result.reputation_bonus_percent, 10)
        self.assertEqual(result.base_cash_reward, 75)
        self.assertEqual(result.cash_bonus, 7)
        self.assertEqual(result.cash_reward, 82)
        self.assertEqual(player.money, 182)

    def test_insufficient_nerve_does_not_attempt_or_change_player(self):
        player = self.make_player(
            nerve=1,
            current_district="soho",
        )
        crime = get_crime("soho_nightclub")
        rng = Mock()

        result = commit_crime(player, crime, rng=rng)

        self.assertFalse(result.attempted)
        self.assertEqual(result.reason, "not_enough_nerve")
        self.assertEqual(player.nerve, 1)
        self.assertEqual(player.money, 100)
        self.assertEqual(player.crime_progress, {})
        rng.randint.assert_not_called()

    def test_failed_crime_can_send_player_to_jail(self):
        player = self.make_player(
            current_district="camden"
        )
        crime = get_crime("camden_shoplift")
        rng = Mock()
        rng.randint.side_effect = [100, 10]

        now = datetime(
            2026,
            8,
            22,
            15,
            0,
            tzinfo=timezone.utc,
        )

        result = commit_crime(
            player,
            crime,
            rng=rng,
            now=now,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.consequence, "jail")
        self.assertEqual(
            result.jail_until,
            "2026-08-22 15:10:00",
        )
        self.assertEqual(
            player.jail_until,
            "2026-08-22 15:10:00",
        )
        self.assertEqual(player.health, 100)
        self.assertEqual(player.money, 100)

    def test_failed_crime_can_send_player_to_hospital(self):
        player = self.make_player()
        crime = get_crime("camden_shoplift")
        rng = Mock()
        rng.randint.side_effect = [100, 1, 9]

        now = datetime(
            2026,
            8,
            22,
            15,
            0,
            tzinfo=timezone.utc,
        )

        result = commit_crime(
            player,
            crime,
            rng=rng,
            now=now,
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.consequence,
            "hospital",
        )
        self.assertEqual(result.damage, 9)
        self.assertEqual(player.health, 91)
        self.assertEqual(
            result.hospital_until,
            "2026-08-22 15:01:00",
        )
        self.assertEqual(
            player.hospital_until,
            "2026-08-22 15:01:00",
        )
        self.assertEqual(player.money, 100)

    def test_crime_is_blocked_while_travelling(self):
        player = self.make_player(
            current_district="brixton"
        )
        player.travel_destination = "brixton"
        player.travel_until = (
            "2026-08-23 12:10:00"
        )

        rng = Mock()

        now = datetime(
            2026,
            8,
            23,
            12,
            0,
            tzinfo=timezone.utc,
        )

        result = commit_crime(
            player,
            get_crime("camden_shoplift"),
            rng=rng,
            now=now,
        )

        self.assertFalse(result.attempted)
        self.assertEqual(
            result.reason,
            "travelling",
        )
        self.assertEqual(player.nerve, 20)
        self.assertEqual(player.money, 100)
        rng.randint.assert_not_called()

    def test_crime_requires_correct_district(self):
        player = self.make_player(
            current_district="camden"
        )
        rng = Mock()

        result = commit_crime(
            player,
            get_crime("soho_pickpocket"),
            rng=rng,
        )

        self.assertFalse(result.attempted)
        self.assertEqual(
            result.reason,
            "wrong_district",
        )
        self.assertEqual(player.nerve, 20)
        self.assertEqual(player.money, 100)
        rng.randint.assert_not_called()

    def test_successful_crime_result_is_displayed(self):
        player = self.make_player(
            current_district="soho"
        )
        crime = get_crime("soho_pickpocket")
        rng = Mock()
        rng.randint.side_effect = [1, 75, 100]

        result = commit_crime(
            player,
            crime,
            rng=rng,
        )

        output = StringIO()

        with redirect_stdout(output):
            display_crime_result(
                player,
                result,
            )

        displayed_text = output.getvalue()

        self.assertIn(
            "Crime successful!",
            displayed_text,
        )
        self.assertIn(
            "You made £ 75",
            displayed_text,
        )
        self.assertIn(
            "XP + 25",
            displayed_text,
        )

if __name__ == "__main__":
    unittest.main()
