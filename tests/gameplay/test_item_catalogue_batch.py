import pathlib

from game.inventory.items import ITEMS, ITEMS_BY_KEY
from game.shop import VENUES


BATCH_ONE_KEYS = {
    "sports_drink", "painkillers", "bandage_roll", "protein_bar",
    "bolt_cutters", "glass_cutter", "burner_phone", "duct_tape",
    "police_baton", "tire_iron", "hatchet", "survival_knife",
    "denim_jacket", "hard_hat", "combat_gloves", "cargo_trousers",
    "trainers", "tactical_boots", "reinforced_jeans", "riot_helmet",
}


def test_first_catalogue_batch_adds_twenty_unique_items():
    assert len(ITEMS) == len(ITEMS_BY_KEY)
    assert len(ITEMS) >= 36
    assert BATCH_ONE_KEYS <= set(ITEMS_BY_KEY)


def test_every_new_equipment_slot_is_valid():
    valid_slots = {"primary", "secondary", "head", "body", "hands", "legs", "feet"}
    for key in BATCH_ONE_KEYS:
        item = ITEMS_BY_KEY[key]
        if item.category in {"weapon", "armour"}:
            assert item.equipment_slot in valid_slots
            assert item.strength_bonus > 0 or item.defence_bonus > 0


def test_all_new_items_are_available_in_a_district_shop():
    stocked = {
        offer.item_key
        for venue in VENUES.values()
        for offer in venue["items"]
    }
    assert BATCH_ONE_KEYS <= stocked


def test_every_shop_offer_has_a_catalogue_definition():
    for venue in VENUES.values():
        for offer in venue["items"]:
            assert offer.item_key in ITEMS_BY_KEY


def test_every_catalogue_item_has_artwork_on_disk():
    static_root = pathlib.Path(__file__).resolve().parents[2] / "web" / "static"
    for item in ITEMS:
        assert (static_root / item.image_filename).is_file(), item.key
