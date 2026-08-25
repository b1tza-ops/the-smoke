import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.market import (
    MarketError,
    buy_listing,
    cancel_listing,
    create_listing,
    get_open_listings,
)
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
    save_player,
)
from database.repositories.users import create_user
from game.economy.market import (
    MAXIMUM_LISTING_QUANTITY,
    commission_on,
    minimum_price,
    seller_proceeds,
)
from game.inventory import INVENTORY_SLOT_CAPACITY, ITEMS, ITEMS_BY_KEY
from game.player import Player


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        create_tables()
        self.seller = self.make("seller", 0, {"machete": 1, "first_aid_kit": 3})
        self.buyer = self.make("buyer", 5_000, {})

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def make(self, name, money, inventory):
        user_id = create_user(name, f"{name}@example.com", "hash")
        create_player(user_id, name.title())
        player = Player(*get_player_by_user_id(user_id))
        player.money = money
        player.inventory = dict(inventory)
        save_player(player)
        return user_id

    def player(self, user_id):
        return Player(*get_player_by_user_id(user_id))

    def list_machete(self, price=1_000):
        return create_listing(self.seller, "machete", 1, price)["id"]

    def statuses(self):
        connection = get_connection()
        try:
            return [
                row[0]
                for row in connection.execute(
                    "SELECT status FROM market_listings ORDER BY id"
                )
            ]
        finally:
            connection.close()

    def test_listing_escrows_the_item_out_of_the_inventory(self):
        self.list_machete()

        self.assertNotIn("machete", self.player(self.seller).inventory)
        self.assertEqual(self.statuses(), ["open"])

    def test_a_sale_moves_cash_and_goods_and_takes_commission(self):
        listing_id = self.list_machete(1_000)

        result = buy_listing(self.buyer, listing_id)

        buyer = self.player(self.buyer)
        seller = self.player(self.seller)
        self.assertEqual(result["total"], 1_000)
        self.assertEqual(result["commission"], commission_on(1_000))
        self.assertEqual(buyer.money, 4_000)
        self.assertEqual(seller.money, seller_proceeds(1_000))
        self.assertEqual(buyer.inventory["machete"], 1)
        self.assertEqual(self.statuses(), ["sold"])

    def test_commission_destroys_money_rather_than_moving_it(self):
        listing_id = self.list_machete(1_000)
        before = self.player(self.buyer).money + self.player(self.seller).money

        buy_listing(self.buyer, listing_id)

        after = self.player(self.buyer).money + self.player(self.seller).money
        self.assertEqual(before - after, commission_on(1_000))

    def test_a_listing_can_only_sell_once(self):
        listing_id = self.list_machete()
        buy_listing(self.buyer, listing_id)

        with self.assertRaises(MarketError):
            buy_listing(self.buyer, listing_id)

        self.assertEqual(self.player(self.buyer).inventory["machete"], 1)

    def test_you_cannot_buy_your_own_listing(self):
        listing_id = self.list_machete()
        seller = self.player(self.seller)
        seller.money = 10_000
        save_player(seller)

        with self.assertRaises(MarketError):
            buy_listing(self.seller, listing_id)

        self.assertEqual(self.statuses(), ["open"])

    def test_a_listing_below_the_fence_price_is_refused(self):
        floor = minimum_price(ITEMS_BY_KEY["machete"])

        with self.assertRaisesRegex(MarketError, "black market"):
            create_listing(self.seller, "machete", 1, floor - 1)

        self.assertEqual(self.player(self.seller).inventory["machete"], 1)
        self.assertEqual(self.statuses(), [])

    def test_invalid_quantities_and_prices_are_refused(self):
        for quantity, price in (
            (0, 1_000),
            (-1, 1_000),
            (True, 1_000),
            (MAXIMUM_LISTING_QUANTITY + 1, 1_000),
            (1, 0),
            (1, True),
        ):
            with self.subTest(quantity=quantity, price=price):
                with self.assertRaises(MarketError):
                    create_listing(self.seller, "machete", quantity, price)

        self.assertEqual(self.statuses(), [])

    def test_listing_more_than_you_own_is_refused(self):
        with self.assertRaises(MarketError):
            create_listing(self.seller, "first_aid_kit", 4, 200)

        self.assertEqual(self.player(self.seller).inventory["first_aid_kit"], 3)

    def test_a_buyer_who_cannot_carry_it_is_refused_outright(self):
        """Unlike loot, a purchase fails loudly rather than paying cash."""
        listing_id = self.list_machete()
        buyer = self.player(self.buyer)
        buyer.inventory = {"machete": 1}
        save_player(buyer)

        with self.assertRaisesRegex(MarketError, "only carry"):
            buy_listing(self.buyer, listing_id)

        self.assertEqual(self.player(self.buyer).money, 5_000)
        self.assertEqual(self.statuses(), ["open"])

    def test_a_full_inventory_refuses_the_purchase(self):
        listing_id = self.list_machete()
        buyer = self.player(self.buyer)
        buyer.inventory = {
            item.key: 1
            for item in ITEMS
            if item.key != "machete"
        }
        buyer.inventory = dict(
            list(buyer.inventory.items())[:INVENTORY_SLOT_CAPACITY]
        )
        save_player(buyer)

        with self.assertRaisesRegex(MarketError, "full"):
            buy_listing(self.buyer, listing_id)

        self.assertEqual(self.statuses(), ["open"])

    def test_a_buyer_short_of_cash_is_refused(self):
        listing_id = self.list_machete(6_000)

        with self.assertRaises(MarketError):
            buy_listing(self.buyer, listing_id)

        self.assertEqual(self.player(self.buyer).money, 5_000)
        self.assertEqual(self.statuses(), ["open"])

    def test_delisting_returns_the_goods(self):
        listing_id = create_listing(self.seller, "first_aid_kit", 2, 200)["id"]
        self.assertEqual(self.player(self.seller).inventory["first_aid_kit"], 1)

        cancel_listing(self.seller, listing_id)

        self.assertEqual(self.player(self.seller).inventory["first_aid_kit"], 3)
        self.assertEqual(self.statuses(), ["cancelled"])

    def test_only_the_seller_can_delist(self):
        listing_id = self.list_machete()

        with self.assertRaises(MarketError):
            cancel_listing(self.buyer, listing_id)

        self.assertEqual(self.statuses(), ["open"])

    def test_a_closed_listing_cannot_be_delisted(self):
        listing_id = self.list_machete()
        buy_listing(self.buyer, listing_id)

        with self.assertRaises(MarketError):
            cancel_listing(self.seller, listing_id)

    def test_trading_is_blocked_while_restricted(self):
        for field in ("jail_until", "hospital_until"):
            with self.subTest(field=field):
                seller = self.player(self.seller)
                setattr(seller, field, "2099-01-01 00:00:00")
                save_player(seller)

                with self.assertRaises(MarketError):
                    create_listing(self.seller, "machete", 1, 1_000)

                seller = self.player(self.seller)
                setattr(seller, field, None)
                save_player(seller)

        self.assertEqual(self.statuses(), [])

    def test_listings_are_cheapest_first_and_flag_your_own(self):
        create_listing(self.seller, "first_aid_kit", 1, 300)
        create_listing(self.seller, "first_aid_kit", 1, 100)

        listings = get_open_listings(self.seller)

        self.assertEqual(
            [listing["price_each"] for listing in listings],
            [100, 300],
        )
        self.assertTrue(all(listing["is_own"] for listing in listings))
        self.assertFalse(
            any(
                listing["is_own"]
                for listing in get_open_listings(self.buyer)
            )
        )

    def test_an_unknown_item_or_listing_is_refused(self):
        with self.assertRaises(MarketError):
            create_listing(self.seller, "not_an_item", 1, 500)

        with self.assertRaises(MarketError):
            buy_listing(self.buyer, 9999)

        with self.assertRaises(MarketError):
            cancel_listing(self.seller, 9999)


if __name__ == "__main__":
    unittest.main()
