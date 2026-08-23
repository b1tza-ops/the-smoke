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


if __name__ == "__main__":
    unittest.main()
