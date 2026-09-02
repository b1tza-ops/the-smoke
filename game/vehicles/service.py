"""Owning a car, and what it costs you to be seen in it.

Pure rules. `database.repositories.vehicles` runs them in a
transaction, and `game.world.travel` asks this module for the mode when
somebody chooses to drive.

Driving is deliberately not a straight upgrade over the Underground.
It is faster, it is cheaper to run, and it reaches Hackney where the
tube does not -- but it is the only way of crossing London that the
police can stop. A wanted player in a Sable GT is a fifty-fifty; the
same player on a bicycle is invisible. That is the whole trade: the
quickest thing on the forecourt is the worst thing to be sitting in
after a job.
"""

from game.housing.service import get_residence
from game.vehicles.definitions import get_vehicle
from game.world.transport import TransportMode


DRIVE_KEY = "drive"

# What the forecourt gives you back. The same half the fence pays for
# stolen goods, for the same reason: a resale that returned most of the
# price would make the garage a savings account with wheels.
RESALE_RATE = 0.5

# Getting stopped costs the journey and a quarter of an hour. Less than
# a failed burglary, because being pulled over is not being caught
# doing anything -- it is being noticed.
PULLED_OVER_SECONDS = 15 * 60

# Nobody is ever certain to be stopped. The worst case in the game is
# maximum heat in the loudest car on the forecourt, and that is a coin
# toss -- which is exactly what the arithmetic below produces, so this
# is the same number rather than a looser one. It stays as a cap so a
# showier vehicle added later cannot push the odds past a coin toss
# without somebody deciding to.
MAXIMUM_STOP_CHANCE = 50

# Divides wanted level times showiness. At the top of both -- 100 heat,
# showiness 10 -- this lands exactly on the cap above.
STOP_DIVISOR = 20


class VehicleError(Exception):
    """Raised when a vehicle cannot be bought, sold or driven."""


def garage_capacity(residence_key):
    """How many vehicles this address will hold.

    Nothing below a van has anywhere to put a car, which is what
    finally makes the garage figure on the property page mean
    something. It also means a vehicle is gated behind a home, and a
    home is gated behind rent.
    """
    residence = get_residence(residence_key)

    return residence.garage_capacity if residence else 0


def garage_room(residence_key, owned):
    return max(0, garage_capacity(residence_key) - max(0, owned))


def resale_value(vehicle):
    return int(vehicle.price * RESALE_RATE)


def stop_chance(vehicle, wanted_level):
    """The odds a patrol pulls this car over, as a percentage.

    Showiness times heat. A bicycle is zero at any wanted level, which
    is the point of keeping one: it is the vehicle you take home from a
    job you are still hot from.
    """
    if vehicle is None:
        return 0

    heat = min(max(0, int(wanted_level or 0)), 100)

    return min(
        MAXIMUM_STOP_CHANCE,
        heat * vehicle.showiness // STOP_DIVISOR,
    )


def driving_mode(vehicle):
    """The transport mode this particular vehicle is.

    Built per vehicle rather than registered as a static mode, because
    a Sable and a bicycle are not the same journey and there is no
    sensible single set of multipliers for "drive".
    """
    if vehicle is None:
        raise VehicleError("You do not have anything to drive.")

    return TransportMode(
        key=DRIVE_KEY,
        name=f"Drive the {vehicle.name}",
        description=vehicle.description,
        fare_multiplier=vehicle.fare_multiplier,
        duration_multiplier=vehicle.duration_multiplier,
    )


def affordable(vehicle, money):
    return vehicle is not None and money >= vehicle.price


def validate_purchase(vehicle_key, level, money, residence_key, owned):
    """Raise unless this player may buy this vehicle right now."""
    vehicle = get_vehicle(vehicle_key)

    if vehicle is None:
        raise VehicleError("They do not sell that.")

    if level < vehicle.minimum_level:
        raise VehicleError(
            f"The {vehicle.name} is for level "
            f"{vehicle.minimum_level} and up."
        )

    if garage_capacity(residence_key) <= 0:
        raise VehicleError(
            "You have nowhere to keep it. A van is the cheapest "
            "address in London with a garage."
        )

    if garage_room(residence_key, owned) <= 0:
        raise VehicleError(
            "Your garage is full. Sell something first."
        )

    if money < vehicle.price:
        raise VehicleError(
            f"The {vehicle.name} is £{vehicle.price:,}. "
            f"You have £{money:,}."
        )

    return vehicle
