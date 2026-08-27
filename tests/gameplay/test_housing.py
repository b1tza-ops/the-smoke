import unittest
from types import SimpleNamespace

from game.housing import (
    RESIDENCES,
    AlreadyLivingThereError,
    InsufficientCashError,
    UnknownResidenceError,
    get_player_residence,
    get_residence,
    purchase_residence,
)


class ResidenceDefinitionTests(unittest.TestCase):
    def test_residence_keys_are_unique(self):
        keys = [
            residence.key
            for residence in RESIDENCES
        ]

        self.assertEqual(
            len(keys),
            len(set(keys)),
        )

    def test_residence_modifiers_can_be_queried(self):
        residence = get_residence("council_flat")

        self.assertEqual(residence.name, "Council Flat")
        self.assertEqual(residence.comfort, 4)
        self.assertEqual(residence.storage_capacity, 20)
        self.assertEqual(
            residence.energy_recovery_bonus_percent,
            10,
        )
        self.assertEqual(
            residence.nerve_recovery_bonus_percent,
            10,
        )
        self.assertEqual(
            residence.safe_cash_capacity,
            2000,
        )
        self.assertEqual(residence.garage_capacity, 1)

    def test_all_residence_values_are_non_negative(self):
        for residence in RESIDENCES:
            with self.subTest(residence=residence.key):
                self.assertGreaterEqual(
                    residence.purchase_price,
                    0,
                )
                self.assertGreaterEqual(
                    residence.comfort,
                    0,
                )
                self.assertGreaterEqual(
                    residence.storage_capacity,
                    0,
                )
                self.assertGreaterEqual(
                    residence.energy_recovery_bonus_percent,
                    0,
                )
                self.assertGreaterEqual(
                    residence.nerve_recovery_bonus_percent,
                    0,
                )
                self.assertGreaterEqual(
                    residence.safe_cash_capacity,
                    0,
                )
                self.assertGreaterEqual(
                    residence.garage_capacity,
                    0,
                )


class HousingEngineTests(unittest.TestCase):
    def make_player(
        self,
        money=500,
        residence_key="tent",
    ):
        return SimpleNamespace(
            money=money,
            residence_key=residence_key,
        )

    def test_player_residence_returns_definition(self):
        player = self.make_player()

        residence = get_player_residence(player)

        self.assertEqual(residence.key, "tent")
        self.assertEqual(residence.name, "Tent")

    def test_purchase_moves_player_and_deducts_cash(self):
        player = self.make_player()

        result = purchase_residence(
            player,
            "hostel",
        )

        self.assertEqual(
            result.previous_residence_key,
            "tent",
        )
        self.assertEqual(
            result.residence_key,
            "hostel",
        )
        self.assertEqual(result.amount_paid, 250)
        self.assertEqual(result.cash_balance, 250)
        self.assertEqual(player.money, 250)
        self.assertEqual(
            player.residence_key,
            "hostel",
        )

    def test_insufficient_cash_does_not_change_player(self):
        player = self.make_player(money=999)

        with self.assertRaises(InsufficientCashError):
            purchase_residence(
                player,
                "council_flat",
            )

        self.assertEqual(player.money, 999)
        self.assertEqual(player.residence_key, "tent")

    def test_current_residence_cannot_be_purchased_again(self):
        player = self.make_player()

        with self.assertRaises(AlreadyLivingThereError):
            purchase_residence(
                player,
                "tent",
            )

        self.assertEqual(player.money, 500)
        self.assertEqual(player.residence_key, "tent")

    def test_unknown_residence_does_not_change_player(self):
        player = self.make_player()

        with self.assertRaises(UnknownResidenceError):
            purchase_residence(
                player,
                "unknown_home",
            )

        self.assertEqual(player.money, 500)
        self.assertEqual(player.residence_key, "tent")

    def test_unknown_player_residence_is_rejected(self):
        player = self.make_player(
            residence_key="missing_home",
        )

        with self.assertRaises(UnknownResidenceError):
            get_player_residence(player)


class ResidenceLadderTests(unittest.TestCase):
    @staticmethod
    def artwork_directory():
        from pathlib import Path as _Path

        return (
            _Path(__file__).resolve().parents[2]
            / "web" / "static" / "images" / "housing"
        )

    """No rung of the ladder may be worse than the one below it.

    The page lists these in order and prices them upwards, so a player
    reads position as improvement. The Converted Van shipped at £1,800
    sitting above the £1,000 Council Flat while being worse at comfort,
    storage, energy recovery and safe capacity -- a trap that costs a
    new player money for a downgrade. This makes that unmergeable
    rather than something to be spotted by eye.
    """

    LADDER = (
        "purchase_price",
        "comfort",
        "storage_capacity",
        "energy_recovery_bonus_percent",
        "nerve_recovery_bonus_percent",
        "safe_cash_capacity",
        "garage_capacity",
    )

    def test_the_ladder_is_listed_in_price_order(self):
        prices = [home.purchase_price for home in RESIDENCES]

        self.assertEqual(
            prices,
            sorted(prices),
            "residences are shown in list order, so a cheaper home "
            "must not appear below a dearer one",
        )

    def test_no_residence_is_beaten_by_a_cheaper_one(self):
        for below, above in zip(RESIDENCES, RESIDENCES[1:]):
            for attribute in self.LADDER:
                with self.subTest(
                    paying_more_for=above.key,
                    than=below.key,
                    attribute=attribute,
                ):
                    self.assertGreaterEqual(
                        getattr(above, attribute),
                        getattr(below, attribute),
                        f"{above.name} costs more than {below.name} "
                        f"but has less {attribute}",
                    )

    def test_every_residence_earns_its_price(self):
        # Equal on every axis would be monotonic and still pointless.
        for below, above in zip(RESIDENCES, RESIDENCES[1:]):
            with self.subTest(residence=above.key):
                self.assertTrue(
                    any(
                        getattr(above, attribute)
                        > getattr(below, attribute)
                        for attribute in self.LADDER[1:]
                    ),
                    f"{above.name} costs more than {below.name} and "
                    f"is better at nothing",
                )

    def test_every_residence_has_artwork_a_browser_can_render(self):
        """Not "the file is there" -- that was the version that lied.

        Eight properties once shipped as unreadable bytes carrying an
        image extension. The guard at the time asked whether the file
        existed, which it did, so the suite stayed green while every
        card on the page rendered as a broken-image icon. Ask the
        format instead.
        """
        from utils.images import is_renderable_image

        broken = [
            f"{home.key}.webp"
            for home in RESIDENCES
            if not is_renderable_image(
                self.artwork_directory() / f"{home.key}.webp"
            )
        ]

        self.assertEqual(
            broken,
            [],
            "the page falls back to a placeholder for these, so nothing "
            "is broken on screen -- but they are not the artwork they "
            "are named after: " + ", ".join(broken),
        )

    def test_nothing_unreadable_is_sitting_in_the_artwork_folder(self):
        # Catches a file that is not claimed by any residence, so a
        # rename or a bad export cannot quietly leave rubbish behind.
        from utils.images import is_renderable_image

        folder = self.artwork_directory()
        unreadable = [
            path.name
            for path in sorted(folder.iterdir())
            if path.is_file() and not is_renderable_image(path)
        ]

        self.assertEqual(unreadable, [], f"unreadable files in {folder}")

    def test_a_residence_without_artwork_still_has_a_name_to_show(self):
        # The placeholder is labelled with the residence name, so a
        # property with no art is still identifiable on the page.
        for home in RESIDENCES:
            with self.subTest(residence=home.key):
                self.assertTrue(home.name.strip())
                self.assertTrue(home.description.strip())


if __name__ == "__main__":
    unittest.main()
