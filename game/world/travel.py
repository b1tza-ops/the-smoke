from dataclasses import dataclass
from datetime import timedelta

from game.world.districts import (
    DISTRICTS,
    get_district,
    get_travel_route,
)

from game.player.regeneration import (
    format_timestamp,
    parse_timestamp,
)
from game.player.status import (
    get_active_restriction,
    normalise_now,
)


class TravelError(Exception):
    """Base exception for travel operations."""


class UnknownDistrictError(TravelError):
    """Raised when a district does not exist."""


class RouteNotFoundError(TravelError):
    """Raised when two districts have no travel route."""


class AlreadyTravellingError(TravelError):
    """Raised when the player is already travelling."""


class SameDistrictError(TravelError):
    """Raised when travelling to the current district."""


class DistrictLockedError(TravelError):
    """Raised when the player's level is too low."""


class InsufficientTravelFundsError(TravelError):
    """Raised when the player cannot afford the journey."""


class TravelRestrictedError(TravelError):
    """Raised when jail or hospital prevents travel."""


@dataclass(frozen=True)
class TravelResult:
    origin_key: str
    destination_key: str
    cost: int
    departed_at: str
    arrives_at: str


@dataclass(frozen=True)
class ActiveTravel:
    origin_key: str
    destination_key: str
    arrives_at: str
    remaining_seconds: int


def update_travel(player, now=None):
    now = normalise_now(now)

    if (
        player.travel_destination is None
        or player.travel_until is None
    ):
        player.travel_destination = None
        player.travel_until = None
        return False

    arrival_time = parse_timestamp(
        player.travel_until
    )

    if arrival_time > now:
        return False

    destination = get_district(
        player.travel_destination
    )

    player.current_district = destination.key
    player.travel_destination = None
    player.travel_until = None

    return True


def get_active_travel(player, now=None):
    now = normalise_now(now)
    update_travel(player, now=now)

    if player.travel_destination is None:
        return None

    remaining_seconds = max(
        0,
        int(
            (
                parse_timestamp(player.travel_until)
                - now
            ).total_seconds()
        ),
    )

    return ActiveTravel(
        origin_key=player.current_district,
        destination_key=player.travel_destination,
        arrives_at=player.travel_until,
        remaining_seconds=remaining_seconds,
    )


def start_travel(
    player,
    destination_key,
    now=None,
):
    now = normalise_now(now)
    update_travel(player, now=now)

    if player.travel_destination is not None:
        raise AlreadyTravellingError(
            "You are already travelling."
        )

    restriction = get_active_restriction(
        player,
        now=now,
    )

    if restriction is not None:
        raise TravelRestrictedError(
            f"You cannot travel while in "
            f"{restriction.kind}."
        )

    try:
        destination = get_district(
            destination_key
        )
    except KeyError as error:
        raise UnknownDistrictError(
            "That district does not exist."
        ) from error

    if destination.key == player.current_district:
        raise SameDistrictError(
            "You are already in that district."
        )

    if player.level < destination.minimum_level:
        raise DistrictLockedError(
            f"{destination.name} requires level "
            f"{destination.minimum_level}."
        )

    try:
        route = get_travel_route(
            player.current_district,
            destination.key,
        )
    except KeyError as error:
        raise RouteNotFoundError(
            "No travel route is available."
        ) from error

    if player.money < route.cost:
        raise InsufficientTravelFundsError(
            "Not enough carried cash for travel."
        )

    departed_at = format_timestamp(now)
    arrives_at = format_timestamp(
        now
        + timedelta(
            seconds=route.duration_seconds
        )
    )

    player.money -= route.cost
    player.travel_destination = destination.key
    player.travel_until = arrives_at

    return TravelResult(
        origin_key=player.current_district,
        destination_key=destination.key,
        cost=route.cost,
        departed_at=departed_at,
        arrives_at=arrives_at,
    )

def travel_menu(player):
    while True:
        active_travel = get_active_travel(player)

        if active_travel is not None:
            remaining_minutes = (
                active_travel.remaining_seconds + 59
            ) // 60

            destination = get_district(
                active_travel.destination_key
            )

            print("\n===== TRAVEL =====")
            print(
                "Travelling to:",
                destination.name,
            )
            print(
                "Arrival time:",
                active_travel.arrives_at,
            )
            print(
                "Approximately",
                remaining_minutes,
                "minute(s) remaining.",
            )
            return

        current = get_district(
            player.current_district
        )

        print("\n===== LONDON TRAVEL =====")
        print("Current location:", current.name)
        print(f"Carried cash: £{player.money:,}")

        destinations = [
            district
            for district in DISTRICTS
            if district.key != current.key
        ]

        for number, district in enumerate(
            destinations,
            start=1,
        ):
            route = get_travel_route(
                current.key,
                district.key,
            )

            duration_minutes = (
                route.duration_seconds + 59
            ) // 60

            locked_text = ""

            if player.level < district.minimum_level:
                locked_text = (
                    f" [Requires level "
                    f"{district.minimum_level}]"
                )

            print(
                f"{number}. {district.name} — "
                f"£{route.cost}, "
                f"{duration_minutes} minute(s)"
                f"{locked_text}"
            )

        back_option = len(destinations) + 1
        print(f"{back_option}. Back")

        choice = input("Choose: ").strip()

        if choice == str(back_option):
            return

        try:
            selected_index = int(choice) - 1
        except ValueError:
            print("\nInvalid option.")
            continue

        if not 0 <= selected_index < len(
            destinations
        ):
            print("\nInvalid option.")
            continue

        destination = destinations[
            selected_index
        ]

        try:
            result = start_travel(
                player,
                destination.key,
            )
        except TravelError as error:
            print(f"\nTravel failed: {error}")
            continue

        print(
            f"\nYou are travelling from "
            f"{get_district(result.origin_key).name} "
            f"to "
            f"{get_district(result.destination_key).name}."
        )
        print(f"Travel cost: £{result.cost:,}")
        print("Arrival time:", result.arrives_at)

        return