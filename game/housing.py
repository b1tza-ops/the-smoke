from dataclasses import dataclass


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
