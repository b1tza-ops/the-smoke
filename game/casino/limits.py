"""Who may gamble, for how much, and how much they can win.

Three guards, all of them economic rather than moral. The level gate
keeps a brand-new player from losing their starting stake in one tap.
The bet ceiling rises with level so the tables stay relevant late
without letting a level 3 wager a fortune. The payout ceiling is a table
maximum: a jackpot mints money from nothing, and a small server cannot
absorb an unbounded one.
"""


MINIMUM_LEVEL = 3
MINIMUM_BET = 10
BET_PER_LEVEL = 250

# No single round pays out more than this, however the paytable reads.
MAXIMUM_PAYOUT = 500_000


class CasinoError(Exception):
    """Raised when a wager cannot be accepted."""


def maximum_bet(level):
    return BET_PER_LEVEL * max(MINIMUM_LEVEL, level)


def validate_bet(level, bet, money):
    """Raise unless this player may stake this much right now."""
    if level < MINIMUM_LEVEL:
        raise CasinoError(
            f"The door staff turn you away. Come back at level {MINIMUM_LEVEL}."
        )
    if isinstance(bet, bool) or not isinstance(bet, int):
        raise CasinoError("Choose a stake.")
    if bet < MINIMUM_BET:
        raise CasinoError(f"The minimum stake is £{MINIMUM_BET}.")

    ceiling = maximum_bet(level)
    if bet > ceiling:
        raise CasinoError(
            f"The table limit for level {level} is £{ceiling:,}."
        )
    if bet > money:
        raise CasinoError("You do not have that much on you.")
    return bet


def capped_payout(payout):
    """Apply the table maximum."""
    return min(payout, MAXIMUM_PAYOUT)
