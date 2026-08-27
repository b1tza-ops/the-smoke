from dataclasses import dataclass

FACILITIES = {
    "interior": ("Superior interior", 1500, "+2 comfort"),
    "hot_tub": ("Hot tub", 3000, "+5% energy recovery"),
    "sauna": ("Sauna", 2500, "+5% nerve recovery"),
    "pool": ("Swimming pool", 8000, "+2% gym gains"),
    "open_bar": ("Open bar", 5000, "+3 comfort"),
}


class HousingError(Exception):
    """Base exception for housing operations."""


class UnknownResidenceError(HousingError):
    """Raised when a residence key is not recognised."""


class AlreadyLivingThereError(HousingError):
    """Raised when the selected residence is already active."""


class InsufficientCashError(HousingError):
    """Raised when the player cannot afford a residence."""


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


@dataclass(frozen=True)
class ResidencePurchaseResult:
    previous_residence_key: str
    residence_key: str
    amount_paid: int
    cash_balance: int


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
        storage_capacity=20,
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
        storage_capacity=24,
        energy_recovery_bonus_percent=5,
        nerve_recovery_bonus_percent=5,
        safe_cash_capacity=500,
        garage_capacity=0,
    ),
    ResidenceDefinition(
        key="van",
        name="Converted Van",
        description=(
            "A discreet van with a bed, lockbox and a quick exit."
        ),
        purchase_price=600,
        comfort=3,
        storage_capacity=28,
        energy_recovery_bonus_percent=7,
        nerve_recovery_bonus_percent=8,
        safe_cash_capacity=1000,
        garage_capacity=1,
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
        storage_capacity=34,
        energy_recovery_bonus_percent=10,
        nerve_recovery_bonus_percent=10,
        safe_cash_capacity=2000,
        garage_capacity=1,
    ),
    ResidenceDefinition(
        key="council_house",
        name="Council House",
        description=(
            "A solid brick house with a small garden and room to grow."
        ),
        purchase_price=4500,
        comfort=5,
        storage_capacity=42,
        energy_recovery_bonus_percent=15,
        nerve_recovery_bonus_percent=15,
        safe_cash_capacity=5000,
        garage_capacity=1,
    ),
    ResidenceDefinition(
        key="apartment",
        name="City Apartment",
        description=(
            "A secure apartment above the noise of the street."
        ),
        purchase_price=12000,
        comfort=6,
        storage_capacity=55,
        energy_recovery_bonus_percent=20,
        nerve_recovery_bonus_percent=20,
        safe_cash_capacity=12000,
        garage_capacity=1,
    ),
    ResidenceDefinition(
        key="modern_house",
        name="Modern House",
        description=(
            "A contemporary London home with proper privacy and space."
        ),
        purchase_price=30000,
        comfort=8,
        storage_capacity=75,
        energy_recovery_bonus_percent=30,
        nerve_recovery_bonus_percent=25,
        safe_cash_capacity=30000,
        garage_capacity=2,
    ),
    ResidenceDefinition(
        key="penthouse",
        name="Penthouse",
        description=(
            "A skyline penthouse: secure, spacious and unmistakably "
            "successful."
        ),
        purchase_price=85000,
        comfort=10,
        storage_capacity=100,
        energy_recovery_bonus_percent=40,
        nerve_recovery_bonus_percent=35,
        safe_cash_capacity=100000,
        garage_capacity=3,
    ),
)


RESIDENCES_BY_KEY = {
    residence.key: residence
    for residence in RESIDENCES
}


def get_residence(residence_key):
    if not isinstance(residence_key, str):
        return None

    return RESIDENCES_BY_KEY.get(residence_key)


def get_player_residence(player):
    residence = get_residence(player.residence_key)

    if residence is None:
        raise UnknownResidenceError(
            "The player's residence is not recognised."
        )

    return residence


def purchase_residence(player, residence_key):
    residence = get_residence(residence_key)

    if residence is None:
        raise UnknownResidenceError(
            "Residence does not exist."
        )

    current_residence = get_player_residence(player)

    if residence.key == current_residence.key:
        raise AlreadyLivingThereError(
            "You already live at this residence."
        )

    if player.money < residence.purchase_price:
        raise InsufficientCashError(
            "Not enough carried cash."
        )

    previous_residence_key = player.residence_key

    player.money -= residence.purchase_price
    player.residence_key = residence.key

    return ResidencePurchaseResult(
        previous_residence_key=previous_residence_key,
        residence_key=residence.key,
        amount_paid=residence.purchase_price,
        cash_balance=player.money,
    )

# Which fittings speed which resource up, and by how much. Kept beside
# the FACILITIES catalogue so the effect a player is sold and the effect
# they get come from one place -- the descriptions above were display
# text for a while, promising bonuses nothing applied.
FACILITY_RECOVERY = {
    "energy": {"hot_tub": 5},
    "nerve": {"sauna": 5},
}


def recovery_bonus(residence, facilities, resource):
    """How much faster a resource refills at home, as a percentage.

    Adds the residence's own bonus to anything fitted inside it, so a
    penthouse with a hot tub beats a penthouse without one.
    """
    if resource not in FACILITY_RECOVERY:
        raise HousingError(f"No recovery bonus for {resource!r}.")

    from_home = getattr(
        residence,
        f"{resource}_recovery_bonus_percent",
        0,
    ) if residence else 0

    from_fittings = sum(
        percent
        for key, percent in FACILITY_RECOVERY[resource].items()
        if key in (facilities or ())
    )

    return from_home + from_fittings


def faster_tick(tick_seconds, bonus_percent):
    """Shorten a regeneration tick by a percentage bonus.

    The bonus shortens the interval rather than fattening the points
    each tick pays, because points are whole numbers and a percentage of
    them is not -- five points a tick plus 8% is five points a tick.
    Time divides cleanly and the caller's arithmetic already carries the
    remainder between loads.
    """
    if bonus_percent <= 0:
        return tick_seconds

    return max(
        1,
        round(tick_seconds * 100 / (100 + bonus_percent)),
    )


def facility_for(facility_key):
    """The definition behind a facility key, or a refusal."""
    facility = FACILITIES.get(facility_key)

    if facility is None:
        raise HousingError("Unknown facility.")

    return facility


def housing_menu(player):
    while True:
        current_residence = get_player_residence(player)

        print("\n===== HOUSING =====")
        print("Current residence:", current_residence.name)
        print("Carried cash: £{:,}".format(player.money))
        print("Comfort:", current_residence.comfort)
        print(
            "Storage:",
            current_residence.storage_capacity,
        )
        print(
            "Energy recovery bonus:",
            f"{current_residence.energy_recovery_bonus_percent}%",
        )
        print(
            "Nerve recovery bonus:",
            f"{current_residence.nerve_recovery_bonus_percent}%",
        )
        print(
            "Safe cash capacity: £{:,}".format(
                current_residence.safe_cash_capacity
            )
        )
        print(
            "Garage spaces:",
            current_residence.garage_capacity,
        )

        print("\nAvailable residences:")

        for number, residence in enumerate(
            RESIDENCES,
            start=1,
        ):
            marker = ""

            if residence.key == player.residence_key:
                marker = " [Current]"

            print(
                f"{number}. {residence.name} "
                f"- £{residence.purchase_price:,}"
                f"{marker}"
            )
            print(
                "   "
                f"Comfort {residence.comfort} | "
                f"Storage {residence.storage_capacity} | "
                f"Energy +{residence.energy_recovery_bonus_percent}% | "
                f"Nerve +{residence.nerve_recovery_bonus_percent}%"
            )

        back_option = len(RESIDENCES) + 1
        print(f"{back_option}. Back")

        choice = input("Choose: ").strip()

        if choice == str(back_option):
            return

        try:
            selected_index = int(choice) - 1
        except ValueError:
            print("\nInvalid option.")
            continue

        if not 0 <= selected_index < len(RESIDENCES):
            print("\nInvalid option.")
            continue

        residence = RESIDENCES[selected_index]

        try:
            result = purchase_residence(
                player,
                residence.key,
            )
        except HousingError as error:
            print(f"\nMove failed: {error}")
            continue

        print(
            "\nYou moved into:",
            residence.name,
        )
        print(
            "Amount paid: £{:,}".format(
                result.amount_paid
            )
        )
        print(
            "Cash remaining: £{:,}".format(
                result.cash_balance
            )
        )
