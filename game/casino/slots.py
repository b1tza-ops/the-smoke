"""The fruit machines.

Three independent reels sharing one weighted strip. Three of a kind pays
by symbol; a pair pays only on the four higher symbols, which is what
lifts the hit rate to roughly one spin in five without handing the game
back to the player.

The paytable was solved rather than guessed: with these weights the
return to player is 91.73%, so the house keeps 8.27% of everything
staked. `tests/gameplay/test_casino.py` recomputes that exactly and
fails if a payout is ever edited without re-checking the arithmetic.
"""

import random
from dataclasses import dataclass


# Symbols in ascending order of value, with how many stops each takes on
# the reel. Rarer symbol, bigger prize.
REEL_WEIGHTS = {
    "pint": 12,
    "cab": 10,
    "bell": 8,
    "crown": 6,
    "diamond": 4,
    "seven": 2,
}

SYMBOL_NAMES = {
    "pint": "Pint",
    "cab": "Black Cab",
    "bell": "Bell",
    "crown": "Crown",
    "diamond": "Diamond",
    "seven": "Lucky Seven",
}

# Multiples of the stake.
THREE_OF_A_KIND = {
    "pint": 4,
    "cab": 7,
    "bell": 15,
    "crown": 36,
    "diamond": 120,
    "seven": 750,
}
PAIR = {
    "bell": 1,
    "crown": 1,
    "diamond": 4,
    "seven": 15,
}

REEL_COUNT = 3
STRIP = tuple(
    symbol for symbol, weight in REEL_WEIGHTS.items() for _ in range(weight)
)


@dataclass(frozen=True)
class SpinResult:
    reels: tuple
    multiplier: int
    payout: int
    line: str


def spin_reels(rng=None):
    rng = rng or random
    return tuple(
        STRIP[rng.randint(0, len(STRIP) - 1)] for _ in range(REEL_COUNT)
    )


def score(reels):
    """The multiplier these reels pay, and what to call the result."""
    first, second, third = reels

    if first == second == third:
        return THREE_OF_A_KIND[first], f"Three {SYMBOL_NAMES[first]}s"

    counts = {}
    for symbol in reels:
        counts[symbol] = counts.get(symbol, 0) + 1
    twin = next((symbol for symbol, n in counts.items() if n == 2), None)

    if twin is not None and twin in PAIR:
        return PAIR[twin], f"Two {SYMBOL_NAMES[twin]}s"

    return 0, "No win"


def play(bet, rng=None):
    reels = spin_reels(rng)
    multiplier, line = score(reels)
    return SpinResult(
        reels=reels,
        multiplier=multiplier,
        payout=bet * multiplier,
        line=line,
    )
