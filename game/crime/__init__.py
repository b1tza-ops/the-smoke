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

__all__ = [
    "CRIMES",
    "CRIMES_BY_KEY",
    "CrimeDefinition",
    "CrimeResult",
    "commit_crime",
    "crimes_menu",
    "display_crime_result",
    "get_crime",
]
