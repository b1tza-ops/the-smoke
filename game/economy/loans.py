"""Ronnie Dell, who lends money in Soho.

Borrowing mints money and interest destroys it, so a loan is only a
sink if it is actually repaid. What stops it being a quiet faucet is
that a debt cannot be walked away from: it never expires, it blocks any
further borrowing, and missing a payment has Ronnie's people put you in
hospital for a while that gets longer each time.

Interest accrues lazily from elapsed time, the same way energy and
nerve do, so nothing here needs a scheduler.
"""

from dataclasses import dataclass
from datetime import timedelta


MINIMUM_LEVEL = 3
MINIMUM_LOAN = 1_000
LOAN_PER_LEVEL = 5_000

# Torn charges 2.5% a week. This game moves in hours rather than days --
# energy refills in five -- so the same rate is charged daily, which
# keeps a loan something a player notices inside a session or two.
DAILY_INTEREST_RATE = 0.025
PAYMENT_PERIOD = timedelta(days=3)

# How long Ronnie puts you in hospital for, by how many payments you
# have missed. The last one repeats.
HOSPITAL_MINUTES = (30, 120, 360, 720)


class LoanError(Exception):
    """Raised when a borrowing or repayment cannot go through."""


@dataclass(frozen=True)
class Loan:
    principal: int
    interest: int
    missed_payments: int = 0

    @property
    def balance(self):
        return self.principal + self.interest

    @property
    def settled(self):
        return self.balance <= 0


def maximum_loan(level):
    return LOAN_PER_LEVEL * max(MINIMUM_LEVEL, level)


def headroom(level, principal):
    """How much more this player may borrow on top of what they owe."""
    return max(0, maximum_loan(level) - principal)


def interest_for(principal, elapsed):
    """Interest accrued on a principal over an elapsed period.

    Charged by the second rather than in whole-day steps, so a player is
    never surprised by a day's interest landing all at once, and paying
    early genuinely costs less.
    """
    if principal <= 0 or elapsed.total_seconds() <= 0:
        return 0
    days = elapsed.total_seconds() / 86_400
    return int(principal * DAILY_INTEREST_RATE * days)


def hospital_minutes(missed_payments):
    index = min(max(missed_payments, 0), len(HOSPITAL_MINUTES) - 1)
    return HOSPITAL_MINUTES[index]


def validate_borrow(level, amount, principal):
    if level < MINIMUM_LEVEL:
        raise LoanError(
            f"Ronnie does not lend below level {MINIMUM_LEVEL}."
        )
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise LoanError("Say how much you want.")
    if amount < MINIMUM_LOAN:
        raise LoanError(f"He does not get out of bed for under £{MINIMUM_LOAN:,}.")

    available = headroom(level, principal)
    if available <= 0:
        raise LoanError("You are already in for as much as he will lend you.")
    if amount > available:
        raise LoanError(
            f"He will go to £{available:,} on top of what you already owe."
        )
    return amount


def validate_repayment(amount, balance, money):
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise LoanError("Say how much you want to pay.")
    if amount < 1:
        raise LoanError("Pay him something.")
    if balance <= 0:
        raise LoanError("You do not owe him anything.")

    # Cap to the balance before checking affordability, so typing a big
    # number to clear a small debt settles it instead of being refused
    # for money the player was never going to be charged.
    amount = min(amount, balance)

    if amount > money:
        raise LoanError("You do not have that on you.")
    return amount


def apply_repayment(loan, amount):
    """Interest first, then principal. Returns the loan afterwards."""
    interest_paid = min(loan.interest, amount)
    principal_paid = min(loan.principal, amount - interest_paid)
    return Loan(
        principal=loan.principal - principal_paid,
        interest=loan.interest - interest_paid,
        missed_payments=loan.missed_payments,
    )


def clears_arrears(loan, amount):
    """Whether paying this much counts as making the payment due.

    The interest is what has to be covered. Paying less than it means
    the balance is still growing and Ronnie is still owed.
    """
    return amount >= loan.interest > 0 or amount >= loan.balance
