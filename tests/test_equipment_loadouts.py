from types import SimpleNamespace

from game.gym import get_training_block
from game.inventory import get_item


def test_equipment_items_define_slots_and_bonuses():
    knife = get_item("kitchen_knife")
    jacket = get_item("padded_jacket")

    assert knife.equipment_slot == "weapon"
    assert knife.strength_bonus == 5
    assert knife.defence_bonus == 0

    assert jacket.equipment_slot == "armour"
    assert jacket.defence_bonus == 5
    assert jacket.strength_bonus == 0


def test_consumables_are_not_equippable():
    first_aid = get_item("first_aid_kit")
    energy_drink = get_item("energy_drink")

    assert first_aid.equipment_slot is None
    assert energy_drink.equipment_slot is None


def test_active_work_shift_blocks_gym_training():
    player = SimpleNamespace(
        shift_until="2026-08-24 18:00:00",
    )

    assert get_training_block(player) == "working a shift"
