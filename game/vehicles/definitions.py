"""What is for sale at Coldharbour Motors.

A car is the third thing money can buy that keeps paying: the gym sells
stats, housing sells recovery, and a vehicle sells *time* -- the minutes
you would otherwise spend sitting on a bus, which is the one resource
this game never regenerates.

Every marque here is invented. The Smoke is a made-up London and the
forecourt is stocked to match.

Two numbers do the work:

  duration    how long the journey takes against the bus, so 0.5 is
              half the time. The Underground is 0.5 and does not reach
              Hackney; a car does.
  showiness   how much attention it draws. This is the price of speed:
              the quickest thing on the forecourt is also the one a
              patrol car notices when you are wanted.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Vehicle:
    key: str
    name: str
    description: str
    price: int
    minimum_level: int
    # Against the bus. Lower is faster.
    duration_multiplier: float
    # Petrol, against the bus fare. The bicycle runs on breakfast.
    fare_multiplier: float
    # 0 (nobody looks twice) to 10 (everybody does).
    showiness: int


VEHICLES = (
    Vehicle(
        key="bicycle",
        name="Second-hand Bicycle",
        description=(
            "Rusted, and the brakes are a suggestion. Slower than the "
            "bus, but it costs nothing to run and no copper has ever "
            "pulled one over."
        ),
        price=250,
        minimum_level=1,
        duration_multiplier=1.2,
        fare_multiplier=0.0,
        showiness=0,
    ),
    Vehicle(
        key="moped",
        name="Delivery Moped",
        description=(
            "Somebody peeled the takeaway livery off it. Cuts through "
            "traffic, drinks almost nothing, and looks like every "
            "other moped in London."
        ),
        price=1_500,
        minimum_level=1,
        duration_multiplier=0.8,
        fare_multiplier=0.2,
        showiness=1,
    ),
    Vehicle(
        key="hatchback",
        name="Corsair Hatchback",
        description=(
            "Two previous owners and a service history that stops in "
            "2019. The first thing on this forecourt with a roof."
        ),
        price=5_000,
        minimum_level=3,
        duration_multiplier=0.6,
        fare_multiplier=0.5,
        showiness=2,
    ),
    Vehicle(
        key="estate",
        name="Marlow Estate",
        description=(
            "Diesel, dented, and the boot swallows anything. Quick "
            "enough, and nobody has ever looked at one twice."
        ),
        price=14_000,
        minimum_level=5,
        duration_multiplier=0.5,
        fare_multiplier=0.7,
        showiness=3,
    ),
    Vehicle(
        key="saloon",
        name="Kestrel Saloon",
        description=(
            "The first car here that is faster than the Underground on "
            "every route, including the ones it does not run on."
        ),
        price=38_000,
        minimum_level=8,
        duration_multiplier=0.4,
        fare_multiplier=0.9,
        showiness=5,
    ),
    Vehicle(
        key="coupe",
        name="Bellamy Coupé",
        description=(
            "Loud, low and the colour of a warning. Halves what the "
            "saloon does and doubles who notices."
        ),
        price=90_000,
        minimum_level=12,
        duration_multiplier=0.32,
        fare_multiplier=1.1,
        showiness=8,
    ),
    Vehicle(
        key="sable",
        name="Sable GT",
        description=(
            "The quickest way across London and the worst possible "
            "thing to be sitting in when you are wanted."
        ),
        price=220_000,
        minimum_level=16,
        duration_multiplier=0.25,
        fare_multiplier=1.4,
        showiness=10,
    ),
)

VEHICLES_BY_KEY = {vehicle.key: vehicle for vehicle in VEHICLES}


def get_vehicle(key):
    return VEHICLES_BY_KEY.get(key)
