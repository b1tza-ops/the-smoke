"""Keno: pick your numbers, the house draws twenty.

Eighty numbers, twenty drawn, and the player picks between two and six.
Picking a single number is deliberately not offered: at one in four
there is no whole-number multiplier between a 75% return and a 100% one,
and a 100% return is a grind with no house edge at all.

Every paytable returns between 90% and 92%, so no spot count is a trap
and none is a loophole. The top prize is capped at 1000x rather than
following the true odds: a jackpot mints money from nothing, and the
one-in-eight-million payouts a real keno board advertises would distort
an economy this size. `tests/gameplay/test_casino.py` recomputes each
table hypergeometrically.
"""

import random
from dataclasses import dataclass


POOL_SIZE = 80
DRAW_SIZE = 20
MINIMUM_SPOTS = 2
MAXIMUM_SPOTS = 6

# {spots picked: {numbers matched: multiple of the stake}}
PAYTABLE = {
    2: {2: 15},
    3: {2: 2, 3: 46},
    4: {2: 1, 3: 5, 4: 160},
    5: {3: 2, 4: 15, 5: 880},
    6: {3: 2, 4: 8, 5: 95, 6: 1000},
}


class KenoError(Exception):
    """Raised when a card cannot be played."""


@dataclass(frozen=True)
class KenoResult:
    picks: tuple
    drawn: tuple
    hits: tuple
    multiplier: int
    payout: int
    line: str


def validate_picks(picks):
    """Normalise and check a player's card."""
    numbers = []
    for value in picks:
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise KenoError("Those are not numbers.")
        if not 1 <= number <= POOL_SIZE:
            raise KenoError(f"Numbers run from 1 to {POOL_SIZE}.")
        numbers.append(number)

    unique = set(numbers)
    if len(unique) != len(numbers):
        raise KenoError("You cannot pick the same number twice.")
    if len(unique) < MINIMUM_SPOTS:
        raise KenoError(f"Pick at least {MINIMUM_SPOTS} numbers.")
    if len(unique) > MAXIMUM_SPOTS:
        raise KenoError(f"Pick at most {MAXIMUM_SPOTS} numbers.")
    return tuple(sorted(unique))


def draw(rng=None):
    """Twenty distinct numbers, drawn without replacement."""
    rng = rng or random
    pool = list(range(1, POOL_SIZE + 1))
    drawn = []
    for _ in range(DRAW_SIZE):
        index = rng.randint(0, len(pool) - 1)
        drawn.append(pool.pop(index))
    return tuple(drawn)


def score(picks, drawn):
    hits = tuple(sorted(set(picks) & set(drawn)))
    multiplier = PAYTABLE[len(picks)].get(len(hits), 0)
    return hits, multiplier


def play(bet, picks, rng=None):
    picks = validate_picks(picks)
    drawn = draw(rng)
    hits, multiplier = score(picks, drawn)
    spots = len(picks)
    return KenoResult(
        picks=picks,
        drawn=drawn,
        hits=hits,
        multiplier=multiplier,
        payout=bet * multiplier,
        line=(
            f"{len(hits)} of {spots}"
            if multiplier
            else f"{len(hits)} of {spots} — no win"
        ),
    )
