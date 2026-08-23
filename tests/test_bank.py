import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.bank import (
    InsufficientBankFundsError,
    InsufficientCashError,
    InvalidAmountError,
    deposit,
    withdraw,
)
from database.connection import get_connection
from database.players import create_player
from database.setup import create_tables
from database.users import create_user


class BankTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_dir.name)
            / "data"
            / "game.db"
        )

        self.database_patch = patch(
            "database.connection.DB_PATH",
            self.database_path
        )
        self.database_patch.start()

        create_tables()

        user_id = create_user(
            username="bank_player",
            email="bank@example.com",
            password_hash="test_hash"
        )

        self.player_id = create_player(
            user_id,
            "Bank Character"
        )

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def get_balances(self):
        conn = get_connection()

        balances = conn.execute(
            """
            SELECT money, bank_balance
            FROM players
            WHERE id = ?
            """,
            (self.player_id,)
        ).fetchone()

        conn.close()
        return balances

    def get_transactions(self):
        conn = get_connection()

        transactions = conn.execute(
            """
            SELECT
                transaction_type,
                amount,
                cash_balance_after,
                bank_balance_after
            FROM bank_transactions
            WHERE player_id = ?
            ORDER BY id
            """,
            (self.player_id,)
        ).fetchall()

        conn.close()
        return transactions

    def test_deposit_moves_cash_and_creates_ledger_entry(self):
        result = deposit(self.player_id, 200)

        self.assertEqual(result.cash_balance, 300)
        self.assertEqual(result.bank_balance, 200)
        self.assertEqual(self.get_balances(), (300, 200))
        self.assertEqual(
            self.get_transactions(),
            [("deposit", 200, 300, 200)]
        )

    def test_insufficient_cash_rolls_back_deposit(self):
        with self.assertRaises(InsufficientCashError):
            deposit(self.player_id, 501)

        self.assertEqual(self.get_balances(), (500, 0))
        self.assertEqual(self.get_transactions(), [])

    def test_withdrawal_moves_bank_money_back_to_cash(self):
        deposit(self.player_id, 200)

        result = withdraw(self.player_id, 75)

        self.assertEqual(result.cash_balance, 375)
        self.assertEqual(result.bank_balance, 125)
        self.assertEqual(self.get_balances(), (375, 125))
        self.assertEqual(
            self.get_transactions(),
            [
                ("deposit", 200, 300, 200),
                ("withdrawal", 75, 375, 125),
            ]
        )

    def test_insufficient_bank_funds_roll_back_withdrawal(self):
        with self.assertRaises(
            InsufficientBankFundsError
        ):
            withdraw(self.player_id, 1)

        self.assertEqual(self.get_balances(), (500, 0))
        self.assertEqual(self.get_transactions(), [])

    def test_invalid_amounts_are_rejected(self):
        invalid_amounts = (
            0,
            -10,
            1.5,
            "10",
            True,
        )

        for amount in invalid_amounts:
            with self.subTest(amount=amount):
                with self.assertRaises(
                    InvalidAmountError
                ):
                    deposit(self.player_id, amount)

        self.assertEqual(self.get_balances(), (500, 0))
        self.assertEqual(self.get_transactions(), [])


if __name__ == "__main__":
    unittest.main()