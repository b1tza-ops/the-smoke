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
    daily_rent: int
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
        daily_rent=0,
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
        daily_rent=150,
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
        daily_rent=175,
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
        daily_rent=200,
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
        daily_rent=250,
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
        daily_rent=310,
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
        daily_rent=400,
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
        daily_rent=550,
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
    # Happiness has no fitting of its own. It runs on comfort, which is
    # what the superior interior and the open bar buy -- see
    # `comfort_for` below.
    "happiness": {},
}

# Comfort each fitting adds on top of the address. These are the
# numbers the shop already advertises; until now nothing read them.
FACILITY_COMFORT = {
    "interior": 2,
    "open_bar": 3,
}

# Happiness recovery, as a percentage, per point of comfort above the
# first. A tent is comfort 1 and gets nothing, which keeps it level
# with its 0% energy and nerve bonuses; a penthouse is comfort 10 and
# gets 36%, which sits alongside its 40% energy. Fitting both the
# interior and the open bar takes that to 56%.
#
# Happiness is what the gym spends alongside energy, so this is the
# quiet way a good address pays for itself: not more gains per train,
# but more trains.
COMFORT_HAPPINESS_PERCENT = 4

# Gym gains each fitting adds, as a percentage. Small on purpose --
# £8,000 should nudge training, not replace the gym ladder.
FACILITY_GYM_GAIN = {
    "pool": 2,
}


def comfort_for(residence, facilities):
    """How comfortable a home is, fittings included."""
    from_home = residence.comfort if residence else 0

    return from_home + sum(
        points
        for key, points in FACILITY_COMFORT.items()
        if key in (facilities or ())
    )


def gym_gain_bonus(facilities):
    """Extra training gain from what is fitted at home, per cent."""
    return sum(
        percent
        for key, percent in FACILITY_GYM_GAIN.items()
        if key in (facilities or ())
    )


def recovery_bonus(residence, facilities, resource):
    """How much faster a resource refills at home, as a percentage.

    Adds the residence's own bonus to anything fitted inside it, so a
    penthouse with a hot tub beats a penthouse without one.

    Happiness is the odd one out: no fitting speeds it directly, so it
    is driven by comfort instead -- which is what finally makes the
    comfort figure on every property mean something.
    """
    if resource not in FACILITY_RECOVERY:
        raise HousingError(f"No recovery bonus for {resource!r}.")

    if resource == "happiness":
        comfort = comfort_for(residence, facilities)

        return max(0, comfort - 1) * COMFORT_HAPPINESS_PERCENT

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


# What a home costs to keep, as a share of what it cost to buy, per day.
# The tent is free forever, so a new player never meets this at all, and
# it only becomes a real number once someone has chosen to own something
# expensive. At 0.3% the penthouse runs about £255 a day -- a fifth of
# what a developed player earns in three hours.
# Arrears are capped so a player who stops playing for a month does not
# come back to a bill they cannot clear. Two weeks of a penthouse is
# £7,700 -- about eight three-hour days of Shoreditch work, which is a
# real setback but not a wall.
MAXIMUM_UPKEEP_ARREARS_DAYS = 14


def daily_upkeep(residence):
    """What this home costs to keep for a day.

    Read from the residence rather than derived from its price, because
    the two ladders have genuinely different shapes and forcing one out
    of the other gave nonsense at both ends.

    House prices span 340x, from a £250 hostel room to an £85,000
    penthouse. Income spans about 1.7x: roughly £585 for a three-hour
    day of Camden crime against £990 for the same in Shoreditch. Rent
    proportional to price therefore cannot start at a figure that means
    anything to a new player without ending at one nobody can pay --
    the old 0.3% rate charged £1 a day at the bottom, which was noise.

    So the ladder is chosen against what a player at each rung actually
    earns: £150 a day for the cheapest room, a quarter of a new
    player's playing day, rising to £550 for the penthouse, over half
    of a developed player's. Owning better costs a larger share of your
    time, which is the point of a sink.
    """
    if residence is None:
        return 0

    return residence.daily_rent


def upkeep_owed(residence, elapsed):
    """Rent accrued over an elapsed period, charged by the second.

    The same lazy accrual the loan shark and every resource clock use:
    nothing is scheduled, it is simply worked out from the last time it
    was settled.
    """
    daily = daily_upkeep(residence)

    if daily <= 0 or elapsed.total_seconds() <= 0:
        return 0

    days = min(
        elapsed.total_seconds() / 86_400,
        MAXIMUM_UPKEEP_ARREARS_DAYS,
    )

    return int(daily * days)


def is_in_arrears(owed):
    """Whether the landlord has stopped doing you any favours.

    Falling behind suspends what the home does for you -- the recovery
    bonus and the extra carrying space -- and nothing else. You are not
    evicted, you lose no items, and paying up restores it immediately.
    A sink that can take your things away is not a sink, it is a trap.
    """
    return owed > 0
