"""Guns v1.0 — the four low-calibre pistols.

Firearms are the first weapons above the machete, and the only ones sold
behind the Hackney Lock-Up counter, so the tests here pin the ladder in
place: price rises with strength, nothing cheaper hits harder, and the
fence still pays less than the shop charges.
"""

import pathlib
import unittest

from game.economy.fence import FENCE_RATE, SPECIALITY_RATE, fence_price
from game.inventory.items import AMMO_KEYS, ITEMS, ITEMS_BY_KEY, weapons_using
from game.shop import DISTRICT_SHOPS, VENUES


PISTOL_KEYS = (
    "derringer_22",
    "converted_blank_pistol",
    "snub_nose_38",
    "compact_9mm",
)

STATIC_ROOT = pathlib.Path(__file__).resolve().parents[2] / "web" / "static"

BAZAAR_KEY = "kingsland_arms"


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
    def test_pistols_are_sold_only_at_the_bazaar(self):
        for key, venue in VENUES.items():
            stocked = {offer.item_key for offer in venue["items"]}
            sold = stocked & set(PISTOL_KEYS)
            if key == BAZAAR_KEY:
                self.assertEqual(sold, set(PISTOL_KEYS))
            else:
                self.assertEqual(sold, set(), f"{key} should not sell guns")

    def test_the_bazaar_is_the_only_source_of_ammunition(self):
        for key, venue in VENUES.items():
            stocked = {offer.item_key for offer in venue["items"]}
            sold = stocked & AMMO_KEYS
            if key == BAZAAR_KEY:
                self.assertEqual(sold, set(AMMO_KEYS))
            else:
                self.assertEqual(sold, set(), f"{key} should not sell ammo")

    def test_the_bazaar_stands_in_hackney(self):
        self.assertEqual(VENUES[BAZAAR_KEY]["district"], "hackney")
        # The Lock-Up is still there, and still sells no firearms.
        self.assertIn("hackney", DISTRICT_SHOPS)

    def test_shop_price_matches_the_catalogue_value(self):
        offers = {
            offer.item_key: offer
            for offer in VENUES[BAZAAR_KEY]["items"]
        }
        for key in PISTOL_KEYS + tuple(sorted(AMMO_KEYS)):
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


class AmmunitionTests(unittest.TestCase):
    def test_every_pistol_is_chambered_for_something_that_exists(self):
        for key in PISTOL_KEYS:
            ammo_key = ITEMS_BY_KEY[key].ammo_key
            self.assertIsNotNone(ammo_key, key)
            self.assertIn(ammo_key, ITEMS_BY_KEY)
            self.assertIn(ammo_key, AMMO_KEYS)

    def test_ammunition_is_derived_from_the_weapons_that_use_it(self):
        self.assertEqual(
            AMMO_KEYS,
            frozenset({"ammo_22", "ammo_9mm", "ammo_38"}),
        )
        for ammo_key in AMMO_KEYS:
            self.assertTrue(weapons_using(ammo_key))

    def test_ammunition_stacks_deep_and_carries_no_bonus(self):
        for ammo_key in AMMO_KEYS:
            item = ITEMS_BY_KEY[ammo_key]
            self.assertTrue(item.stackable)
            self.assertGreaterEqual(item.max_quantity, 100)
            self.assertEqual(item.strength_bonus, 0)
            self.assertEqual(item.defence_bonus, 0)
            self.assertIsNone(item.equipment_slot)
            self.assertIsNone(item.ammo_key)

    def test_ammunition_art_is_installed(self):
        for ammo_key in AMMO_KEYS:
            path = STATIC_ROOT / ITEMS_BY_KEY[ammo_key].image_filename
            self.assertTrue(path.is_file(), f"missing art for {ammo_key}")

    def test_the_nine_mil_feeds_two_guns_so_an_upgrade_keeps_the_calibre(self):
        # Buying the Compact 9mm should not strand a stock of rounds.
        self.assertEqual(
            {item.key for item in weapons_using("ammo_9mm")},
            {"converted_blank_pistol", "compact_9mm"},
        )

    def test_a_round_costs_a_small_fraction_of_what_a_fight_pays(self):
        # The weakest opponent pays 30-55, so a round must not eat the purse.
        for ammo_key in AMMO_KEYS:
            self.assertLess(ITEMS_BY_KEY[ammo_key].value, 30)


if __name__ == "__main__":
    unittest.main()
