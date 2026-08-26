"""Guns are dead weight without the right rounds in the bag.

The rule has two halves that have to agree: an unloaded firearm must
contribute nothing to a fight, and a fight must actually spend a round.
These tests pin both, plus the arithmetic that decides which calibre a
given loadout burns.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
    save_player,
)
from database.repositories.users import create_user
from game.inventory.equipment import equip_item, get_equipment_summary
from game.inventory.items import AMMO_KEYS, ITEMS_BY_KEY
from game.inventory.service import add_item, spend_ammo
from game.player import Player
from game.shop import ShopError, VENUES, purchase_at
from game.world.city import directory


class AmmunitionTestCase(unittest.TestCase):
    """A real database, because the ammo check is a live inventory read."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database_path = Path(self.temp_dir.name) / "ammo.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        self.user_id = create_user("gunner", "gunner@example.com", "hash")
        create_player(self.user_id, "Gunner")
        self.player = self.reload()

    def reload(self):
        return Player(*get_player_by_user_id(self.user_id))

    def give(self, item_key, quantity=1):
        player = self.reload()
        add_item(player, item_key, quantity)
        save_player(player)
        return player

    def arm_with(self, weapon_key, ammo_key=None, rounds=0):
        self.give(weapon_key)
        if ammo_key and rounds:
            self.give(ammo_key, rounds)
        player = self.reload()
        equip_item(player.id, weapon_key)
        return player

    def summary(self):
        return get_equipment_summary(self.reload().id)


class UnloadedWeaponTests(AmmunitionTestCase):
    def test_a_gun_with_no_rounds_contributes_nothing(self):
        self.arm_with("compact_9mm")
        summary = self.summary()

        self.assertEqual(summary.strength_bonus, 0)
        self.assertTrue(summary.has_unloaded_weapon)
        self.assertEqual(
            [item.key for item in summary.unloaded], ["compact_9mm"]
        )
        self.assertEqual(summary.ammo_in_use, ())

    def test_the_wrong_calibre_does_not_load_a_gun(self):
        self.arm_with("compact_9mm", "ammo_38", 25)
        summary = self.summary()

        self.assertEqual(summary.strength_bonus, 0)
        self.assertEqual(
            [item.key for item in summary.unloaded], ["compact_9mm"]
        )

    def test_a_single_round_is_enough_to_load_a_gun(self):
        self.arm_with("compact_9mm", "ammo_9mm", 1)
        summary = self.summary()

        self.assertEqual(summary.strength_bonus, 22)
        self.assertEqual(summary.unloaded, ())
        self.assertEqual(summary.ammo_in_use, ("ammo_9mm",))

    def test_the_gun_stays_equipped_while_it_is_inert(self):
        self.arm_with("derringer_22")
        summary = self.summary()

        # It is still in the slot, so the character sheet can explain why.
        self.assertEqual(summary.items["primary"].key, "derringer_22")
        self.assertEqual(summary.strength_bonus, 0)

    def test_melee_weapons_never_need_feeding(self):
        self.arm_with("machete")
        summary = self.summary()

        self.assertEqual(summary.strength_bonus, 15)
        self.assertEqual(summary.unloaded, ())
        self.assertEqual(summary.ammo_in_use, ())

    def test_armour_keeps_working_while_the_gun_is_empty(self):
        self.give("stab_vest")
        self.arm_with("compact_9mm")
        player = self.reload()
        equip_item(player.id, "stab_vest")
        summary = self.summary()

        self.assertEqual(summary.strength_bonus, 0)
        self.assertGreater(summary.defence_bonus, 0)


class SpendingRoundsTests(AmmunitionTestCase):
    def test_a_fight_spends_exactly_one_round(self):
        self.arm_with("compact_9mm", "ammo_9mm", 3)
        player = self.reload()
        spent = spend_ammo(player, get_equipment_summary(player.id))
        save_player(player)

        self.assertEqual(len(spent), 1)
        self.assertEqual(spent[0].item_key, "ammo_9mm")
        self.assertEqual(spent[0].name, "9mm Rounds")
        self.assertEqual(spent[0].remaining, 2)
        self.assertEqual(self.reload().inventory["ammo_9mm"], 2)

    def test_an_unloaded_gun_spends_nothing(self):
        self.arm_with("compact_9mm")
        player = self.reload()

        self.assertEqual(spend_ammo(player, get_equipment_summary(player.id)), ())

    def test_a_melee_loadout_spends_nothing(self):
        self.arm_with("machete")
        player = self.reload()

        self.assertEqual(spend_ammo(player, get_equipment_summary(player.id)), ())

    def test_the_last_round_leaves_the_gun_inert(self):
        self.arm_with("snub_nose_38", "ammo_38", 1)
        player = self.reload()
        spend_ammo(player, get_equipment_summary(player.id))
        save_player(player)

        summary = self.summary()
        self.assertEqual(summary.strength_bonus, 0)
        self.assertEqual(
            [item.key for item in summary.unloaded], ["snub_nose_38"]
        )

    def test_spending_survives_the_stock_vanishing_underneath_it(self):
        # The summary is taken before the fight; the rounds could be gone
        # by the time it resolves. That must not raise into the fight path.
        self.arm_with("compact_9mm", "ammo_9mm", 1)
        loaded = get_equipment_summary(self.reload().id)

        player = self.reload()
        player.inventory.pop("ammo_9mm")
        save_player(player)

        player = self.reload()
        self.assertEqual(spend_ammo(player, loaded), ())


class BazaarSupplyTests(AmmunitionTestCase):
    def setUp(self):
        super().setUp()
        player = self.reload()
        player.level = 9
        player.current_district = "hackney"
        player.money = 40000
        save_player(player)

    def test_rounds_can_be_bought_by_the_hundred(self):
        result = purchase_at(self.user_id, "kingsland_arms", "ammo_9mm", 120)

        self.assertEqual(result["quantity"], 120)
        self.assertEqual(result["total"], 120 * 16)
        self.assertEqual(self.reload().inventory["ammo_9mm"], 120)

    def test_a_gun_cannot_be_bought_from_a_district_store(self):
        with self.assertRaises(ShopError):
            purchase_at(self.user_id, "hackney_lockup", "compact_9mm", 1)

    def test_the_bazaar_cannot_be_reached_from_another_district(self):
        player = self.reload()
        player.current_district = "camden"
        save_player(player)

        with self.assertRaises(ShopError):
            purchase_at(self.user_id, "kingsland_arms", "ammo_9mm", 10)

    def test_buying_beyond_the_carry_limit_is_refused(self):
        limit = ITEMS_BY_KEY["ammo_9mm"].max_quantity
        purchase_at(self.user_id, "kingsland_arms", "ammo_9mm", limit)

        with self.assertRaises(ShopError):
            purchase_at(self.user_id, "kingsland_arms", "ammo_9mm", 1)


class CityDirectoryTests(unittest.TestCase):
    def test_the_bazaar_is_listed_where_it_stands(self):
        sections = directory("hackney")
        here = sections[0]

        self.assertEqual(here.title, "Hackney")
        self.assertIn(
            "gun_bazaar", {place.endpoint for place in here.destinations}
        )

    def test_the_bazaar_is_flagged_as_a_journey_from_elsewhere(self):
        sections = directory("camden")
        away = [section for section in sections if not section.reachable]

        self.assertEqual(len(away), 1)
        self.assertIn(
            "gun_bazaar", {place.endpoint for place in away[0].destinations}
        )

    def test_every_district_gets_a_directory_with_no_duplicates(self):
        for venue in VENUES.values():
            sections = directory(venue["district"])
            endpoints = [
                place.endpoint
                for section in sections
                for place in section.destinations
            ]
            self.assertEqual(len(endpoints), len(set(endpoints)))

    def test_the_local_section_is_named_after_the_district(self):
        self.assertEqual(directory("soho")[0].title, "Soho")


if __name__ == "__main__":
    unittest.main()
