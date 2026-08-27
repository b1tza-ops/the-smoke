"""Housing definitions, purchases, and playable menu."""

from game.housing.service import (
    FACILITIES,
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
    facility_for,
)

__all__ = [
    "RESIDENCES",
    "FACILITIES",
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
    "facility_for",
]
