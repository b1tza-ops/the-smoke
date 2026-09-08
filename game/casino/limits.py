"""Who may gamble, for how much, and how much they can win.

Three guards, all of them economic rather than moral. The level gate
keeps a brand-new player from losing their starting stake in one tap.
The bet ceiling rises with level so the tables stay relevant late
without letting a level 3 wager a fortune. The payout ceiling is a table
maximum on the winnings: a jackpot mints money from nothing, and a small
server cannot absorb an unbounded one. It bounds what comes back above
the stake rather than the gross return, because blackjack can have eight
bets on the table at once and a ceiling on the gross would eat into
those.
"""


MINIMUM_LEVEL = 3
MINIMUM_BET = 10
BET_PER_LEVEL = 250

# No single round hands back more than this above its stake, however
# the paytable reads.
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


def capped_payout(payout, staked):
    """Apply the table maximum to the winnings, never to the stake.

    The ceiling exists to bound what the house mints, and what it mints
    is the money handed back *above* what was put down. Capping the
    gross return instead has a sharp edge on it, because a blackjack
    table is not one bet: split to four hands and doubled on each, it
    holds eight times the opening stake. Trim that gross return to the
    ceiling and a player who won every hand gets back less than they
    staked -- the house keeping money off a table it lost outright.

    Slots and keno never risk more than a single bet, so the old
    arithmetic was right everywhere it was ever exercised. It was wrong
    only on the one game that can stake eight bets at once, and only
    once somebody was big enough to reach it, which is the kind of bug
    that waits quietly for its first victim.
    """
    if payout <= staked:
        return payout

    return staked + min(payout - staked, MAXIMUM_PAYOUT)


# The chips on the rail. A player picks a denomination rather than typing
# a number, so the ones above their ceiling are shown but dead.
DENOMINATIONS = (10, 50, 100, 500, 1_000, 5_000, 10_000, 50_000)


def denominations(level):
    """Every chip, with whether this player may stake it."""
    ceiling = maximum_bet(level)
    return tuple(
        (amount, amount <= ceiling)
        for amount in DENOMINATIONS
        if amount >= MINIMUM_BET
    )
