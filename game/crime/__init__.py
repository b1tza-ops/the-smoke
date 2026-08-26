"""Crime definitions, outcomes, and playable menu."""

from game.crime.service import (
    CRIMES,
    CRIMES_BY_KEY,
    CrimeDefinition,
    CrimeResult,
    commit_crime,
    crimes_menu,
    display_crime_result,
    get_crime,
)
from game.crime.progression import (
    MASTERY_TIERS,
    MAX_REPUTATION_BONUS_PERCENT,
    MAX_SUCCESS_CHANCE,
    CrimeProgression,
    crime_progression_for,
)

__all__ = [
    "CRIMES",
    "CRIMES_BY_KEY",
    "CrimeDefinition",
    "CrimeResult",
    "commit_crime",
    "crimes_menu",
    "display_crime_result",
    "get_crime",
    "MASTERY_TIERS",
    "MAX_REPUTATION_BONUS_PERCENT",
    "MAX_SUCCESS_CHANCE",
    "CrimeProgression",
    "crime_progression_for",
]
