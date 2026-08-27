import unittest

from types import SimpleNamespace

from game.gym import get_training_block
from game.inventory import EQUIPMENT_SLOTS, get_item


class EquipmentLoadoutTests(unittest.TestCase):

    def test_equipment_items_define_specific_slots_and_bonuses(self):
        knife = get_item("kitchen_knife")
        machete = get_item("machete")
        jacket = get_item("padded_jacket")
        gloves = get_item("leather_gloves")
        boots = get_item("work_boots")
        helmet = get_item("motorcycle_helmet")

        assert EQUIPMENT_SLOTS == (
            "primary", "secondary", "melee", "throwable",
            "head", "body", "hands", "legs", "feet",
        )
        assert knife.equipment_slot == "melee"
        assert knife.strength_bonus == 5
        assert machete.equipment_slot == "melee"
        assert jacket.equipment_slot == "body"
        assert jacket.defence_bonus == 5
        assert gloves.equipment_slot == "hands"
        assert boots.equipment_slot == "feet"
        assert helmet.equipment_slot == "head"

    def test_consumables_are_not_equippable(self):
        first_aid = get_item("first_aid_kit")
        energy_drink = get_item("energy_drink")

        assert first_aid.equipment_slot is None
        assert energy_drink.equipment_slot is None

    def test_active_work_shift_blocks_gym_training(self):
        player = SimpleNamespace(
            shift_until="2026-08-24 18:00:00",
        )

        assert get_training_block(player) == "working a shift"


if __name__ == "__main__":
    unittest.main()
