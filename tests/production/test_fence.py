import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.fence import (
    MAXIMUM_SALE_QUANTITY,
    FenceError,
    sell_to_fence,
)
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
    save_player,
)
from database.repositories.users import create_user
from game.economy.fence import fence_price
from game.inventory import ITEMS_BY_KEY
from game.player import Player


class FenceSaleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        create_tables()
        self.user_id = create_user("fencer", "fencer@example.com", "hash")
        create_player(self.user_id, "Fencer")
        self.stock({"machete": 2, "first_aid_kit": 3})

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def stock(self, inventory):
        player = self.player()
        player.inventory = dict(inventory)
        save_player(player)

    def player(self):
        return Player(*get_player_by_user_id(self.user_id))

    def ledger(self):
        connection = get_connection()
        try:
            return connection.execute(
                "SELECT COUNT(*) FROM fence_transactions"
            ).fetchone()[0]
        finally:
            connection.close()

    def test_a_sale_pays_out_and_removes_the_item_once(self):
        before = self.player().money
        expected = fence_price(ITEMS_BY_KEY["machete"], "camden")

        result = sell_to_fence(self.user_id, "camden", "machete", 1)

        after = self.player()
        self.assertEqual(result["payout"], expected)
        self.assertEqual(after.money, before + expected)
        self.assertEqual(after.inventory["machete"], 1)
        self.assertEqual(self.ledger(), 1)

    def test_selling_the_last_one_clears_the_stack(self):
        sell_to_fence(self.user_id, "camden", "machete", 2)

        self.assertNotIn("machete", self.player().inventory)

    def test_the_district_decides_the_rate(self):
        player = self.player()
        player.current_district = "hackney"
        save_player(player)

        result = sell_to_fence(self.user_id, "hackney", "machete", 1)

        # Hackney deals in weapons, so it pays the premium.
        self.assertEqual(
            result["payout"],
            fence_price(ITEMS_BY_KEY["machete"], "hackney"),
        )
        self.assertGreater(
            result["payout"],
            fence_price(ITEMS_BY_KEY["machete"], "camden"),
        )

    def test_selling_more_than_you_own_changes_nothing(self):
        before = self.player().money

        with self.assertRaises(FenceError):
            sell_to_fence(self.user_id, "camden", "machete", 3)

        after = self.player()
        self.assertEqual(after.money, before)
        self.assertEqual(after.inventory["machete"], 2)
        self.assertEqual(self.ledger(), 0)

    def test_invalid_quantities_are_refused(self):
        for quantity in (0, -1, True, MAXIMUM_SALE_QUANTITY + 1):
            with self.subTest(quantity=quantity):
                with self.assertRaises(FenceError):
                    sell_to_fence(
                        self.user_id,
                        "camden",
                        "first_aid_kit",
                        quantity,
                    )

        self.assertEqual(self.ledger(), 0)

    def test_you_must_be_in_the_district(self):
        with self.assertRaises(FenceError):
            sell_to_fence(self.user_id, "hackney", "machete", 1)

        self.assertEqual(self.player().inventory["machete"], 2)

    def test_you_cannot_deal_while_travelling_or_restricted(self):
        for field in ("travel_destination", "jail_until", "hospital_until"):
            with self.subTest(field=field):
                player = self.player()
                setattr(
                    player,
                    field,
                    "soho" if field == "travel_destination"
                    else "2099-01-01 00:00:00",
                )
                save_player(player)

                with self.assertRaises(FenceError):
                    sell_to_fence(self.user_id, "camden", "machete", 1)

                player = self.player()
                setattr(player, field, None)
                save_player(player)

        self.assertEqual(self.ledger(), 0)

    def test_an_unknown_item_or_district_is_refused(self):
        with self.assertRaises(FenceError):
            sell_to_fence(self.user_id, "camden", "not_an_item", 1)

        with self.assertRaises(FenceError):
            sell_to_fence(self.user_id, "atlantis", "machete", 1)


if __name__ == "__main__":
    unittest.main()
