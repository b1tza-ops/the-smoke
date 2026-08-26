"""The Golden Square: slots, keno and blackjack.

Every game is a pure module with an injectable rng, so the outcome maths
is testable without a database and the return to player can be recomputed
exactly rather than trusted. Money only moves in
`database.repositories.casino`, inside one transaction per round.
"""

from game.casino.limits import (
    BET_PER_LEVEL,
    MAXIMUM_PAYOUT,
    MINIMUM_BET,
    MINIMUM_LEVEL,
    CasinoError,
    capped_payout,
    maximum_bet,
    validate_bet,
)

GAMES = ("slots", "keno", "blackjack")

__all__ = [
    "BET_PER_LEVEL",
    "GAMES",
    "MAXIMUM_PAYOUT",
    "MINIMUM_BET",
    "MINIMUM_LEVEL",
    "CasinoError",
    "capped_payout",
    "maximum_bet",
    "validate_bet",
]
