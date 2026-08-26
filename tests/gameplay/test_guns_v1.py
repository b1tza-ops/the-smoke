"""Guns v1.0 — the four low-calibre pistols.

Firearms are the first weapons above the machete, and the only ones sold
behind the Hackney Lock-Up counter, so the tests here pin the ladder in
place: price rises with strength, nothing cheaper hits harder, and the
fence still pays less than the shop charges.
"""

import pathlib
import unittest

from game.economy.fence import FENCE_RATE, SPECIALITY_RATE, fence_price
from game.inventory.items import ITEMS, ITEMS_BY_KEY
from game.shop import DISTRICT_SHOPS


PISTOL_KEYS = (
    "derringer_22",
    "converted_blank_pistol",
    "snub_nose_38",
    "compact_9mm",
)

STATIC_ROOT = pathlib.Path(__file__).resolve().parents[2] / "web" / "static"


class GunCatalogueTests(unittest.TestCase):
    def test_every_pistol_is_a_primary_weapon(self):
        for key in PISTOL_KEYS:
            item = ITEMS_BY_KEY[key]
            self.assertEqual(item.category, "weapon")
            self.assertEqual(item.equipment_slot, "primary")
            self.assertFalse(item.stackable)
            self.assertEqual(item.max_quantity, 1)
            self.assertEqual(item.defence_bonus, 0)

    def test_pistol_art_is_installed(self):
        for key in PISTOL_KEYS:
            path = STATIC_ROOT / ITEMS_BY_KEY[key].image_filename
            self.assertTrue(path.is_file(), f"missing art for {key}")

    def test_price_rises_with_strength(self):
        ladder = [ITEMS_BY_KEY[key] for key in PISTOL_KEYS]
        strengths = [item.strength_bonus for item in ladder]
        values = [item.value for item in ladder]
        self.assertEqual(strengths, sorted(strengths))
        self.assertEqual(values, sorted(values))
        self.assertEqual(len(set(strengths)), len(strengths))

    def test_pistols_sit_above_every_melee_weapon(self):
        pistols = {ITEMS_BY_KEY[key] for key in PISTOL_KEYS}
        melee = [
            item for item in ITEMS
            if item.category == "weapon" and item not in pistols
        ]
        strongest_melee = max(item.strength_bonus for item in melee)
        dearest_melee = max(item.value for item in melee)
        for item in pistols:
            self.assertGreater(item.strength_bonus, strongest_melee)
            self.assertGreater(item.value, dearest_melee)


class GunSupplyTests(unittest.TestCase):
    def test_pistols_are_sold_only_at_the_hackney_lock_up(self):
        for district, shop in DISTRICT_SHOPS.items():
            stocked = {offer.item_key for offer in shop["items"]}
            sold = stocked & set(PISTOL_KEYS)
            if district == "hackney":
                self.assertEqual(sold, set(PISTOL_KEYS))
            else:
                self.assertEqual(sold, set(), f"{district} should not sell guns")

    def test_shop_price_matches_the_catalogue_value(self):
        offers = {
            offer.item_key: offer
            for offer in DISTRICT_SHOPS["hackney"]["items"]
        }
        for key in PISTOL_KEYS:
            self.assertEqual(offers[key].price, ITEMS_BY_KEY[key].value)

    def test_fencing_a_pistol_never_beats_buying_one(self):
        for key in PISTOL_KEYS:
            item = ITEMS_BY_KEY[key]
            for district in DISTRICT_SHOPS:
                self.assertLess(fence_price(item, district), item.value)
            # Hackney deals in weapons, so it pays the better rate.
            self.assertEqual(
                fence_price(item, "hackney"),
                int(item.value * SPECIALITY_RATE),
            )
            self.assertEqual(
                fence_price(item, "camden"),
                int(item.value * FENCE_RATE),
            )


if __name__ == "__main__":
    unittest.main()
