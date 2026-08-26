import unittest

from game.economy.fence import FENCE_RATE, fence_price
from game.economy.market import (
    COMMISSION_RATE,
    MAXIMUM_LISTING_QUANTITY,
    commission_on,
    minimum_price,
    seller_proceeds,
    validate_listing,
)
from game.inventory import ITEMS, ITEMS_BY_KEY


class CommissionTests(unittest.TestCase):
    def test_the_house_takes_its_percentage(self):
        self.assertEqual(commission_on(1_000), 50)
        self.assertEqual(seller_proceeds(1_000), 950)

    def test_commission_rounds_in_the_houses_favour(self):
        # 999 x 5% is 49.95, and the house does not round down.
        self.assertEqual(commission_on(999), 50)
        self.assertEqual(seller_proceeds(999), 949)

    def test_even_the_smallest_sale_pays_something(self):
        self.assertGreaterEqual(commission_on(1), 1)

    def test_the_seller_never_receives_more_than_was_paid(self):
        for total in (1, 7, 100, 999, 1_000, 250_000):
            with self.subTest(total=total):
                self.assertLess(seller_proceeds(total), total)
                self.assertEqual(
                    seller_proceeds(total) + commission_on(total),
                    total,
                )

    def test_the_rate_is_five_percent(self):
        self.assertEqual(COMMISSION_RATE, 0.05)


class MinimumPriceTests(unittest.TestCase):
    def test_the_floor_is_what_the_fence_would_pay(self):
        for item in ITEMS:
            with self.subTest(item=item.key):
                self.assertEqual(
                    minimum_price(item),
                    max(1, int(item.value * FENCE_RATE)),
                )

    def test_a_speciality_fence_can_still_beat_a_floor_listing(self):
        """The floor is the *base* fence rate, not the best one.

        So carrying a weapon to Hackney still pays more than dumping it
        on the market at the minimum -- which is what keeps the district
        fences worth walking to.
        """
        machete = ITEMS_BY_KEY["machete"]

        self.assertGreater(
            fence_price(machete, "hackney"),
            minimum_price(machete),
        )
        self.assertEqual(
            fence_price(machete, "camden"),
            minimum_price(machete),
        )


class ListingValidationTests(unittest.TestCase):
    def setUp(self):
        self.machete = ITEMS_BY_KEY["machete"]
        self.kit = ITEMS_BY_KEY["first_aid_kit"]

    def test_a_sensible_listing_passes(self):
        validate_listing(self.machete, 1, minimum_price(self.machete))

    def test_quantity_must_be_a_positive_whole_number(self):
        for quantity in (0, -1, True, 1.5, "2"):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    validate_listing(self.kit, quantity, 500)

    def test_price_must_be_a_whole_number(self):
        for price in (True, 12.5, "500"):
            with self.subTest(price=price):
                with self.assertRaises(ValueError):
                    validate_listing(self.kit, 1, price)

    def test_a_listing_cannot_exceed_the_batch_limit(self):
        with self.assertRaises(ValueError):
            validate_listing(
                self.kit,
                MAXIMUM_LISTING_QUANTITY + 1,
                500,
            )

    def test_a_listing_cannot_exceed_what_anyone_could_carry(self):
        # A machete is limited to one, so two can never be a listing.
        with self.assertRaisesRegex(ValueError, "carry"):
            validate_listing(self.machete, 2, 1_000)

    def test_undercutting_the_fence_is_refused(self):
        with self.assertRaisesRegex(ValueError, "black market"):
            validate_listing(
                self.machete,
                1,
                minimum_price(self.machete) - 1,
            )


if __name__ == "__main__":
    unittest.main()
