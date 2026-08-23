from dataclasses import dataclass

from database.connection import get_connection


class BankError(Exception):
    """Base exception for bank operations."""


class InvalidAmountError(BankError):
    """Raised when an amount is not a positive whole number."""


class InsufficientCashError(BankError):
    """Raised when the player lacks enough carried cash."""


class InsufficientBankFundsError(BankError):
    """Raised when the bank balance is too low."""


class PlayerNotFoundError(BankError):
    """Raised when the requested player does not exist."""


@dataclass(frozen=True)
class BankTransactionResult:
    transaction_type: str
    amount: int
    cash_balance: int
    bank_balance: int


def validate_amount(amount):
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise InvalidAmountError(
            "Amount must be a whole number."
        )

    if amount <= 0:
        raise InvalidAmountError(
            "Amount must be greater than zero."
        )


def deposit(player_id, amount):
    validate_amount(amount)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            """
            SELECT money, bank_balance
            FROM players
            WHERE id = ?
            """,
            (player_id,)
        )

        balances = cursor.fetchone()

        if balances is None:
            raise PlayerNotFoundError(
                "Player does not exist."
            )

        cash_balance, bank_balance = balances

        if amount > cash_balance:
            raise InsufficientCashError(
                "Not enough carried cash."
            )

        new_cash_balance = cash_balance - amount
        new_bank_balance = bank_balance + amount

        cursor.execute(
            """
            UPDATE players
            SET
                money = ?,
                bank_balance = ?
            WHERE id = ?
            """,
            (
                new_cash_balance,
                new_bank_balance,
                player_id
            )
        )

        cursor.execute(
            """
            INSERT INTO bank_transactions (
                player_id,
                transaction_type,
                amount,
                cash_balance_after,
                bank_balance_after
            )
            VALUES (?, 'deposit', ?, ?, ?)
            """,
            (
                player_id,
                amount,
                new_cash_balance,
                new_bank_balance
            )
        )

        conn.commit()

        return BankTransactionResult(
            transaction_type="deposit",
            amount=amount,
            cash_balance=new_cash_balance,
            bank_balance=new_bank_balance
        )

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def withdraw(player_id, amount):
    validate_amount(amount)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            """
            SELECT money, bank_balance
            FROM players
            WHERE id = ?
            """,
            (player_id,)
        )

        balances = cursor.fetchone()

        if balances is None:
            raise PlayerNotFoundError(
                "Player does not exist."
            )

        cash_balance, bank_balance = balances

        if amount > bank_balance:
            raise InsufficientBankFundsError(
                "Not enough money in the bank."
            )

        new_cash_balance = cash_balance + amount
        new_bank_balance = bank_balance - amount

        cursor.execute(
            """
            UPDATE players
            SET
                money = ?,
                bank_balance = ?
            WHERE id = ?
            """,
            (
                new_cash_balance,
                new_bank_balance,
                player_id
            )
        )

        cursor.execute(
            """
            INSERT INTO bank_transactions (
                player_id,
                transaction_type,
                amount,
                cash_balance_after,
                bank_balance_after
            )
            VALUES (?, 'withdrawal', ?, ?, ?)
            """,
            (
                player_id,
                amount,
                new_cash_balance,
                new_bank_balance
            )
        )

        conn.commit()

        return BankTransactionResult(
            transaction_type="withdrawal",
            amount=amount,
            cash_balance=new_cash_balance,
            bank_balance=new_bank_balance
        )

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()