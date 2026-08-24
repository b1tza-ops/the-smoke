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
        rng.randint.side_effect = lambda low, high: high

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
        rng.randint.side_effect = lambda low, high: high
        result = fight_player(
            attacker, defender,
            self.empty_equipment, self.empty_equipment,
            "aggressive", reward_multiplier=0.0, rng=rng,
        )
        self.assertEqual(result.cash_stolen, 0)
        self.assertEqual(result.xp_reward, 5)

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
        rng.randint.side_effect = lambda low, high: high
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


if __name__ == "__main__":
    unittest.main()
