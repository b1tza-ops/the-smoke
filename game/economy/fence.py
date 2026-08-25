"""The black market: where stolen goods turn back into cash.

Legitimate shops do not buy anything, so this is the only guaranteed way
to sell. It is deliberately the *floor* of the selling economy -- instant,
always available, and poor value. The player market, where another player
sets the price, is the ceiling.

Every fence pays a fraction of the item's value, and value is the cheapest
price any shop charges. That is what stops a player buying in one district
and fencing in another for profit: even the best fence rate is below the
lowest shop price, so the round trip always loses money.
"""

from dataclasses import dataclass


# What a fence pays, as a fraction of the item's value.
FENCE_RATE = 0.5

# What a fence pays for the sort of goods it actually deals in. Still
# below the cheapest shop price, so it cannot be arbitraged.
SPECIALITY_RATE = 0.65


@dataclass(frozen=True)
class FenceDefinition:
    key: str
    name: str
    district: str
    strapline: str
    specialities: frozenset[str]

    def rate_for(self, category):
        if category in self.specialities:
            return SPECIALITY_RATE

        return FENCE_RATE


FENCES = (
    FenceDefinition(
        key="camden_lock_market",
        name="Camden Lock Market",
        district="camden",
        strapline=(
            "A stall at the back of the market that asks no questions "
            "about where the shopping came from."
        ),
        specialities=frozenset({"boost", "medical"}),
    ),
    FenceDefinition(
        key="brixton_railway_arch",
        name="The Railway Arch",
        district="brixton",
        strapline=(
            "Tools and hardware, in through one door and out through "
            "another the same afternoon."
        ),
        specialities=frozenset({"weapon"}),
    ),
    FenceDefinition(
        key="soho_back_room",
        name="The Back Room",
        district="soho",
        strapline=(
            "Behind a Soho pharmacy counter, where medicine and quiet "
            "tools both find buyers by morning."
        ),
        specialities=frozenset({"medical", "utility"}),
    ),
    FenceDefinition(
        key="shoreditch_unit_nine",
        name="Unit Nine",
        district="shoreditch",
        strapline=(
            "A studio unit that takes electronics off your hands and "
            "never asks for a serial number."
        ),
        specialities=frozenset({"utility"}),
    ),
    FenceDefinition(
        key="hackney_towpath",
        name="The Towpath",
        district="hackney",
        strapline=(
            "Serious kit only. They pay properly and they expect you "
            "to be gone within the minute."
        ),
        specialities=frozenset({"weapon", "armour"}),
    ),
)

FENCES_BY_DISTRICT = {fence.district: fence for fence in FENCES}


def get_fence(district_key):
    return FENCES_BY_DISTRICT.get(district_key)


def fence_price(item, district_key):
    """What the fence in a district pays for one of an item.

    Falls back to the base rate for a district with no fence, so a new
    district cannot make an item silently worthless.
    """
    fence = get_fence(district_key)
    rate = (
        fence.rate_for(item.category)
        if fence is not None
        else FENCE_RATE
    )

    return int(item.value * rate)
