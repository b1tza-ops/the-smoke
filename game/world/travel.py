from dataclasses import dataclass
from datetime import timedelta
import random

from game.world.districts import (
    DISTRICTS,
    get_district,
    get_travel_route,
)
from game.world.transport import (
    DEFAULT_TRANSPORT_KEY,
    get_transport_mode,
    serves,
)
from game.vehicles.service import (
    DRIVE_KEY,
    PULLED_OVER_SECONDS,
    driving_mode,
    stop_chance,
)

from game.player.regeneration import (
    format_timestamp,
    parse_timestamp,
)
from game.player.status import (
    get_active_restriction,
    normalise_now,
    send_to_jail,
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


class UnknownTransportError(TravelError):
    """Raised when a transport mode does not exist."""


class TransportUnavailableError(TravelError):
    """Raised when a mode does not serve a route."""


class PulledOverError(TravelError):
    """Raised when the police stop the journey before it starts."""


@dataclass(frozen=True)
class TravelResult:
    origin_key: str
    destination_key: str
    cost: int
    departed_at: str
    arrives_at: str
    mode_key: str = DEFAULT_TRANSPORT_KEY
    mode_name: str = "Bus"


@dataclass(frozen=True)
class ActiveTravel:
    origin_key: str
    destination_key: str
    arrives_at: str
    remaining_seconds: int
    mode_key: str = DEFAULT_TRANSPORT_KEY
    mode_name: str = "Bus"


def update_travel(player, now=None):
    now = normalise_now(now)

    if (
        player.travel_destination is None
        or player.travel_until is None
    ):
        player.travel_destination = None
        player.travel_until = None
        player.travel_mode = None
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
    player.travel_mode = None

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

    mode = get_transport_mode(
        getattr(player, "travel_mode", None)
        or DEFAULT_TRANSPORT_KEY
    )

    return ActiveTravel(
        origin_key=player.current_district,
        destination_key=player.travel_destination,
        arrives_at=player.travel_until,
        remaining_seconds=remaining_seconds,
        mode_key=mode.key if mode else DEFAULT_TRANSPORT_KEY,
        mode_name=mode.name if mode else "Bus",
    )


def start_travel(
    player,
    destination_key,
    mode_key=DEFAULT_TRANSPORT_KEY,
    now=None,
    vehicle=None,
    rng=None,
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

    if mode_key == DRIVE_KEY:
        # Built from the car rather than looked up, because a bicycle
        # and a Sable GT are not the same journey.
        if vehicle is None:
            raise TransportUnavailableError(
                "You have nothing in the garage to drive."
            )
        mode = driving_mode(vehicle)
    else:
        mode = get_transport_mode(mode_key)

    if mode is None:
        raise UnknownTransportError(
            "That is not a way of getting there."
        )

    if not serves(mode, player.current_district, destination.key):
        raise TransportUnavailableError(
            f"The {mode.name} does not run to {destination.name}."
        )

    fare = mode.fare(route)

    if player.money < fare:
        raise InsufficientTravelFundsError(
            "Not enough carried cash for travel."
        )

    if mode.key == DRIVE_KEY:
        # Checked before any money moves: being stopped costs the
        # journey and a quarter of an hour, never the petrol as well.
        chance = stop_chance(vehicle, player.wanted_level)
        roll = (rng or random.SystemRandom()).randint(1, 100)

        if chance and roll <= chance:
            send_to_jail(player, PULLED_OVER_SECONDS, now=now)
            raise PulledOverError(
                f"A patrol pulls the {vehicle.name} over before you "
                "reach the end of the road. You are wanted, and they "
                "know it."
            )

    departed_at = format_timestamp(now)
    arrives_at = format_timestamp(
        now
        + timedelta(
            seconds=mode.duration_seconds(route)
        )
    )

    player.money -= fare
    player.travel_destination = destination.key
    player.travel_until = arrives_at
    player.travel_mode = mode.key

    return TravelResult(
        origin_key=player.current_district,
        destination_key=destination.key,
        cost=fare,
        departed_at=departed_at,
        arrives_at=arrives_at,
        mode_key=mode.key,
        mode_name=mode.name,
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