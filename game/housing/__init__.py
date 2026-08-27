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
    player_facilities,
    purchase_facility,
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
    "player_facilities",
    "purchase_facility",
]
