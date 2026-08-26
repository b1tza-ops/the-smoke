"""How you get across London.

Every route can be walked, and the walk is free. What money buys is the
time back: the bus is the middle option, and the Underground halves the
journey for double the fare.

That matters most at the bottom of the game. A player with nothing can
always move -- they pay for it in minutes they cannot spend on anything
else, since travel blocks crimes, training and work.
"""

from dataclasses import dataclass


# Districts the Underground does not reach. Hackney has no tube station
# -- it is Overground and buses out there -- so the fastest way east is
# still the bus, however rich you are.
NO_UNDERGROUND = frozenset({"hackney"})


@dataclass(frozen=True)
class TransportMode:
    key: str
    name: str
    description: str
    fare_multiplier: float
    duration_multiplier: float

    def fare(self, route):
        return int(route.cost * self.fare_multiplier)

    def duration_seconds(self, route):
        return max(
            60,
            int(route.duration_seconds * self.duration_multiplier),
        )


TRANSPORT_MODES = (
    TransportMode(
        key="walk",
        name="Walk",
        description="Free, and you will feel every minute of it.",
        fare_multiplier=0.0,
        duration_multiplier=3.0,
    ),
    TransportMode(
        key="bus",
        name="Bus",
        description="Slow, cheap and it goes everywhere.",
        fare_multiplier=1.0,
        duration_multiplier=1.0,
    ),
    TransportMode(
        key="underground",
        name="Underground",
        description="Double the fare, half the journey.",
        fare_multiplier=2.0,
        duration_multiplier=0.5,
    ),
)

TRANSPORT_MODES_BY_KEY = {
    mode.key: mode
    for mode in TRANSPORT_MODES
}

DEFAULT_TRANSPORT_KEY = "bus"


def get_transport_mode(mode_key):
    return TRANSPORT_MODES_BY_KEY.get(mode_key)


def serves(mode, origin_key, destination_key):
    if mode.key != "underground":
        return True

    return not (
        NO_UNDERGROUND & {origin_key, destination_key}
    )


def available_modes(origin_key, destination_key):
    return tuple(
        mode
        for mode in TRANSPORT_MODES
        if serves(mode, origin_key, destination_key)
    )
