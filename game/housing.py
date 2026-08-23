from dataclasses import dataclass


@dataclass(frozen=True)
class ResidenceDefinition:
    key: str
    name: str
    description: str
    purchase_price: int
    comfort: int
    storage_capacity: int
    energy_recovery_bonus_percent: int
    nerve_recovery_bonus_percent: int
    safe_cash_capacity: int
    garage_capacity: int


RESIDENCES = (
    ResidenceDefinition(
        key="tent",
        name="Tent",
        description=(
            "A battered tent on the edge of Camden. "
            "It offers little comfort, but it is free."
        ),
        purchase_price=0,
        comfort=1,
        storage_capacity=5,
        energy_recovery_bonus_percent=0,
        nerve_recovery_bonus_percent=0,
        safe_cash_capacity=100,
        garage_capacity=0,
    ),
    ResidenceDefinition(
        key="hostel",
        name="Hostel Room",
        description=(
            "A small shared room with a lockable cupboard "
            "and somewhere warm to sleep."
        ),
        purchase_price=250,
        comfort=2,
        storage_capacity=10,
        energy_recovery_bonus_percent=5,
        nerve_recovery_bonus_percent=5,
        safe_cash_capacity=500,
        garage_capacity=0,
    ),
    ResidenceDefinition(
        key="council_flat",
        name="Council Flat",
        description=(
            "A modest London flat with private storage "
            "and space for a small vehicle."
        ),
        purchase_price=1000,
        comfort=4,
        storage_capacity=20,
        energy_recovery_bonus_percent=10,
        nerve_recovery_bonus_percent=10,
        safe_cash_capacity=2000,
        garage_capacity=1,
    ),
)


RESIDENCES_BY_KEY = {
    residence.key: residence
    for residence in RESIDENCES
}


def get_residence(residence_key):
    return RESIDENCES_BY_KEY.get(residence_key)