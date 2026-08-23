"""Housing definitions, purchases, and playable menu."""

from game.housing.service import (
    RESIDENCES,
    RESIDENCES_BY_KEY,
    AlreadyLivingThereError,
    HousingError,
    InsufficientCashError,
    ResidenceDefinition,
    ResidencePurchaseResult,
    UnknownResidenceError,
    get_player_residence,
    get_residence,
    housing_menu,
    purchase_residence,
)

__all__ = [
    "RESIDENCES",
    "RESIDENCES_BY_KEY",
    "AlreadyLivingThereError",
    "HousingError",
    "InsufficientCashError",
    "ResidenceDefinition",
    "ResidencePurchaseResult",
    "UnknownResidenceError",
    "get_player_residence",
    "get_residence",
    "housing_menu",
    "purchase_residence",
]
