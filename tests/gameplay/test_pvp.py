import random
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from game.combat.pvp import (
    PVP_ENERGY_COST,
    PvpError,
    estimate_target,
    fight_player,
    get_pvp_block,
)


def player(player_id, **changes):
    values = {
        "id": player_id,
        "level": 2,
        "money": 500,
        "health": 100,
        "energy": 100,
        "strength": 20,
        "defence": 18,
        "speed": 16,
        "dexterity": 15,
        "current_district": "camden",
        "hospital_until": None,
        "jail_until": None,
        "travel_destination": None,
        "shift_until": None,
        "xp": 100,
    }
    values.update(changes)
    return SimpleNamespace(**values)


class PvpCombatTests(unittest.TestCase):
    def setUp(self):
        self.empty_equipment = SimpleNamespace(
            strength_bonus=0,
            defence_bonus=0,
        )

    def test_attack_spends_energy_and_awards_only_carried_cash(self):
        attacker = player(1, strength=80, dexterity=80)
        defender = player(2, money=1000, strength=1, defence=1)
        rng = Mock()
        rng.randint.side_effect = lambda low, high: low

        result = fight_player(
            attacker, defender,
            self.empty_equipment, self.empty_equipment,
            "aggressive", rng=rng,
        )

        self.assertTrue(result.victory)
        self.assertEqual(attacker.energy, 100 - PVP_ENERGY_COST)
        self.assertGreater(result.cash_stolen, 0)
        self.assertLessEqual(result.cash_stolen, 500)
        self.assertEqual(
            attacker.money, 500 + result.cash_stolen
        )
        self.assertIsNotNone(defender.hospital_until)

    def test_reduced_multiplier_reduces_rewards(self):
        attacker = player(1, strength=80, dexterity=80)
        defender = player(2, money=1000, strength=1, defence=1)
        rng = Mock()
        rng.randint.side_effect = lambda low, high: low
        result = fight_player(
            attacker, defender,
            self.empty_equipment, self.empty_equipment,
            "aggressive", reward_multiplier=0.0, rng=rng,
        )
        self.assertEqual(result.cash_stolen, 0)
        self.assertEqual(result.xp_reward, 0)

    def test_work_hospital_travel_and_jail_block_attacks(self):
        target = player(2)
        for field in (
            "shift_until", "hospital_until",
            "jail_until", "travel_destination",
        ):
            attacker = player(1, **{field: "active"})
            self.assertIsNotNone(get_pvp_block(attacker, target))

    def test_target_must_be_in_same_district(self):
        with self.assertRaisesRegex(PvpError, "district"):
            fight_player(
                player(1), player(2, current_district="soho"),
                self.empty_equipment, self.empty_equipment,
                "defensive",
            )

    def test_structured_rounds_support_visual_playback(self):
        attacker = player(1, strength=80, dexterity=80)
        defender = player(2, strength=1, defence=1)
        rng = Mock()
        rng.randint.side_effect = lambda low, high: low
        result = fight_player(
            attacker, defender,
            self.empty_equipment, self.empty_equipment,
            "precise", rng=rng,
        )
        self.assertTrue(result.rounds)
        first = result.rounds[0]
        self.assertGreaterEqual(first.round_number, 1)
        self.assertIn(first.actor, {"attacker", "defender"})
        self.assertIn(first.event, {"hit", "miss", "dodge"})

    def test_playback_carries_each_fighters_health_scale(self):
        """Maximum health grows with level, so it cannot be assumed.

        Without this the arena drew a bar as `health%`, which overflows
        its track and reads "140/100" for a levelled-up fighter.
        """
        attacker = player(
            1, level=5, health=140, max_health=140,
        )
        defender = player(
            2, level=1, health=100, max_health=100,
        )

        result = fight_player(
            attacker, defender,
            self.empty_equipment, self.empty_equipment,
            "precise", rng=random.Random(3),
        )

        self.assertEqual(result.attacker_start_health, 140)
        self.assertEqual(result.attacker_max_health, 140)
        self.assertEqual(result.defender_start_health, 100)
        self.assertEqual(result.defender_max_health, 100)

        for event in result.rounds:
            self.assertLessEqual(
                event.attacker_health, result.attacker_max_health,
            )
            self.assertLessEqual(
                event.defender_health, result.defender_max_health,
            )

    def test_playback_falls_back_when_max_health_is_absent(self):
        attacker = player(1, health=90)
        defender = player(2, health=100)

        result = fight_player(
            attacker, defender,
            self.empty_equipment, self.empty_equipment,
            "precise", rng=random.Random(3),
        )

        self.assertEqual(result.attacker_max_health, 90)
        self.assertEqual(result.defender_max_health, 100)

    def test_difficulty_estimate_is_relative(self):
        attacker = player(1)
        self.assertEqual(
            estimate_target(attacker, player(2)),
            "Even match",
        )
        self.assertEqual(
            estimate_target(
                attacker,
                player(
                    2, strength=100, defence=100,
                    speed=100, dexterity=100,
                ),
            ),
            "Dangerous",
        )


class PvpPlaybackPayloadTests(unittest.TestCase):
    """The shape handed to the arena's replay script."""

    def build(self, **overrides):
        from web.application import build_pvp_playback
        from game.combat.pvp import CombatRound, PvpResult

        values = dict(
            victory=True,
            attacker_health=60,
            defender_health=0,
            cash_stolen=25,
            xp_reward=30,
            rounds=(
                CombatRound(1, "attacker", "hit", 40, 140, 60),
                CombatRound(2, "defender", "miss", 0, 140, 60),
                CombatRound(2, "attacker", "hit", 60, 140, 0),
            ),
            hospital_until=None,
            attacker_start_health=140,
            attacker_max_health=140,
            defender_start_health=100,
            defender_max_health=100,
        )
        values.update(overrides)
        return build_pvp_playback(PvpResult(**values))

    def test_payload_carries_both_health_scales(self):
        payload = self.build()

        self.assertEqual(payload["max_health"]["attacker"], 140)
        self.assertEqual(payload["max_health"]["defender"], 100)
        self.assertEqual(payload["start_health"]["attacker"], 140)
        self.assertEqual(payload["start_health"]["defender"], 100)

    def test_payload_counts_rounds_not_events(self):
        payload = self.build()

        self.assertEqual(len(payload["rounds"]), 3)
        self.assertEqual(payload["total_rounds"], 2)

    def test_payload_is_json_serialisable(self):
        import json

        self.assertIn('"victory": true', json.dumps(self.build()))

    def test_no_fight_produces_no_payload(self):
        from web.application import build_pvp_playback

        self.assertIsNone(build_pvp_playback(None))

    def test_a_fight_with_no_rounds_still_reports_one_round(self):
        payload = self.build(rounds=())

        self.assertEqual(payload["total_rounds"], 1)
        self.assertEqual(payload["rounds"], [])


if __name__ == "__main__":
    unittest.main()
