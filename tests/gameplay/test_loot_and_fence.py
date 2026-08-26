from types import SimpleNamespace
import random
import unittest
from unittest.mock import Mock

from game.crime import commit_crime, get_crime
from game.crime.loot import LOOT_TABLES, roll_loot, validate_tables
from game.economy.fence import (
    FENCE_RATE,
    FENCES,
    SPECIALITY_RATE,
    fence_price,
    get_fence,
)
from game.inventory import INVENTORY_SLOT_CAPACITY, ITEMS, ITEMS_BY_KEY
from game.shop import DISTRICT_SHOPS, VENUES
from game.world.districts import DISTRICTS


class ItemValueTests(unittest.TestCase):
    def test_every_item_is_worth_something(self):
        for item in ITEMS:
            with self.subTest(item=item.key):
                self.assertGreater(item.value, 0)

    def test_value_is_the_cheapest_shop_price(self):
        cheapest = {}

        for venue in VENUES.values():
            for line in venue["items"]:
                cheapest[line.item_key] = min(
                    cheapest.get(line.item_key, line.price),
                    line.price,
                )

        for item in ITEMS:
            with self.subTest(item=item.key):
                self.assertEqual(item.value, cheapest[item.key])


class FenceTests(unittest.TestCase):
    def test_every_district_has_a_fence(self):
        self.assertEqual(
            {fence.district for fence in FENCES},
            {district.key for district in DISTRICTS},
        )

    def test_a_fence_pays_more_for_what_it_deals_in(self):
        hackney = get_fence("hackney")
        machete = ITEMS_BY_KEY["machete"]

        self.assertIn("weapon", hackney.specialities)
        self.assertEqual(
            fence_price(machete, "hackney"),
            int(machete.value * SPECIALITY_RATE),
        )
        self.assertEqual(
            fence_price(machete, "camden"),
            int(machete.value * FENCE_RATE),
        )
        self.assertGreater(
            fence_price(machete, "hackney"),
            fence_price(machete, "camden"),
        )

    def test_buying_anywhere_and_fencing_anywhere_loses_money(self):
        """The invariant that makes cross-district arbitrage pointless.

        Value is the cheapest shop price, and the best fence rate is
        below 1, so the round trip can never turn a profit.
        """
        for venue in VENUES.values():
            for line in venue["items"]:
                item = ITEMS_BY_KEY[line.item_key]

                for district in DISTRICT_SHOPS:
                    with self.subTest(item=item.key, fence=district):
                        self.assertLess(
                            fence_price(item, district),
                            line.price,
                        )

    def test_an_unknown_district_still_pays_the_base_rate(self):
        item = ITEMS_BY_KEY["machete"]

        self.assertEqual(
            fence_price(item, "not_a_district"),
            int(item.value * FENCE_RATE),
        )


class LootTableTests(unittest.TestCase):
    def test_the_tables_are_valid(self):
        validate_tables()

    def test_every_crime_has_a_pool(self):
        for crime_key, (chance, pool) in LOOT_TABLES.items():
            with self.subTest(crime=crime_key):
                self.assertTrue(0 < chance <= 100)
                self.assertTrue(pool)

    def test_a_seeded_roll_is_repeatable(self):
        first = [
            roll_loot("camden_shoplift", random.Random(11))
            for _ in range(5)
        ]
        second = [
            roll_loot("camden_shoplift", random.Random(11))
            for _ in range(5)
        ]

        self.assertEqual(first, second)

    def test_the_drop_rate_matches_the_table(self):
        rng = random.Random(3)
        chance, _ = LOOT_TABLES["camden_shoplift"]
        drops = sum(
            roll_loot("camden_shoplift", rng) is not None
            for _ in range(2000)
        )

        self.assertAlmostEqual(drops / 2000, chance / 100, delta=0.04)

    def test_an_unknown_crime_drops_nothing(self):
        self.assertIsNone(roll_loot("not_a_crime", random.Random(1)))

    def test_higher_tier_crimes_carry_more_valuable_pools(self):
        def pool_value(crime_key):
            _, pool = LOOT_TABLES[crime_key]
            return sum(ITEMS_BY_KEY[key].value for key in pool) / len(pool)

        self.assertLess(
            pool_value("camden_shoplift"),
            pool_value("brixton_warehouse"),
        )
        self.assertLess(
            pool_value("brixton_warehouse"),
            pool_value("hackney_canal_handover"),
        )


class CrimeLootTests(unittest.TestCase):
    def make_player(self, **overrides):
        values = {
            "level": 5,
            "money": 0,
            "nerve": 20,
            "energy": 150,
            "health": 100,
            "max_health": 100,
            "xp": 0,
            "strength": 10,
            "defence": 10,
            "speed": 10,
            "dexterity": 10,
            "current_district": "brixton",
            "travel_destination": None,
            "travel_until": None,
            "wanted_level": 0,
            "last_wanted_update": None,
            "jail_until": None,
            "hospital_until": None,
            "crime_progress": {},
            "district_reputation": {},
            "inventory": {},
            "happiness": 100,
            "max_happiness": 100,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def rng_for(self, cash=300, loot_roll=1, pool_index=3):
        rng = Mock()
        rng.randint.side_effect = [1, cash, loot_roll, pool_index]
        return rng

    def test_loot_lands_in_the_inventory(self):
        player = self.make_player()

        result = commit_crime(
            player,
            get_crime("brixton_warehouse"),
            rng=self.rng_for(),
        )

        self.assertEqual(result.loot_item_key, "crowbar")
        self.assertEqual(result.loot_cash, 0)
        self.assertEqual(player.inventory["crowbar"], 1)
        self.assertEqual(player.money, 300)

    def test_a_duplicate_of_a_one_only_item_pays_cash(self):
        player = self.make_player(inventory={"crowbar": 1})

        result = commit_crime(
            player,
            get_crime("brixton_warehouse"),
            rng=self.rng_for(),
        )

        expected = fence_price(ITEMS_BY_KEY["crowbar"], "brixton")
        self.assertEqual(result.loot_item_key, "crowbar")
        self.assertEqual(result.loot_cash, expected)
        self.assertEqual(player.inventory, {"crowbar": 1})
        self.assertEqual(player.money, 300 + expected)

    def test_a_full_inventory_pays_cash(self):
        filler = {
            item.key: 1
            for item in ITEMS
            if item.key != "crowbar"
        }
        player = self.make_player(
            inventory=dict(
                list(filler.items())[:INVENTORY_SLOT_CAPACITY]
            ),
        )

        result = commit_crime(
            player,
            get_crime("brixton_warehouse"),
            rng=self.rng_for(),
        )

        self.assertGreater(result.loot_cash, 0)
        self.assertNotIn("crowbar", player.inventory)
        self.assertEqual(len(player.inventory), INVENTORY_SLOT_CAPACITY)

    def test_a_failed_crime_drops_nothing(self):
        player = self.make_player()
        rng = Mock()
        rng.randint.side_effect = [100, 100, 8]

        result = commit_crime(
            player,
            get_crime("brixton_warehouse"),
            rng=rng,
        )

        self.assertFalse(result.success)
        self.assertIsNone(result.loot_item_key)
        self.assertEqual(result.loot_cash, 0)
        self.assertEqual(player.inventory, {})

    def test_an_empty_loot_roll_leaves_the_result_clean(self):
        player = self.make_player()
        rng = Mock()
        rng.randint.side_effect = [1, 300, 100]

        result = commit_crime(
            player,
            get_crime("brixton_warehouse"),
            rng=rng,
        )

        self.assertTrue(result.success)
        self.assertIsNone(result.loot_item_key)
        self.assertEqual(result.loot_cash, 0)
        self.assertEqual(player.money, 300)


if __name__ == "__main__":
    unittest.main()
