"""Breaking into somebody's house.

The first thing in this game one player can do to another that is not a
fight. It is crime-shaped rather than combat-shaped -- it costs nerve,
it risks a cell, and the kit in your pockets matters -- and it is the
only reason the safe is a decision rather than a second bank.

The numbers are all aimed at one thing: a burglary should hurt enough
to be worth doing and never enough to end anybody's week. A victim
loses a slice of what they chose to leave at home. Whatever is in the
bank was never at risk, and that is the lesson the mechanic teaches.
"""

from dataclasses import dataclass

from game.crime.tools import TOOL_SUCCESS_BONUS, usable_tools


BURGLARY_NERVE_COST = 8

# Before the target's locks are counted. A tent dweller is a coin flip
# plus a bit; a penthouse is hard work.
BURGLARY_BASE_CHANCE = 60

# What a home takes off that chance. Written out per residence rather
# than derived, so the ladder can be read at a glance and tuned without
# untangling an expression.
HOME_SECURITY = {
    "tent": 0,
    "hostel": 5,
    "van": 8,
    "council_flat": 12,
    "council_house": 18,
    "apartment": 25,
    "modern_house": 32,
    "penthouse": 40,
}

# Kit that helps you through a door. The burner phone and the duct tape
# are for other kinds of job.
BURGLARY_TOOLS = ("lockpick", "glass_cutter", "bolt_cutters")

# What comes out of a safe that is cracked. A share, then a hard
# ceiling: twenty per cent of a full penthouse safe would be £20,000 in
# one visit, which is somebody's week rather than a setback.
BURGLARY_TAKE_PERCENT = 20
BURGLARY_TAKE_CAP = 5_000

# Below this, a safe is not worth the nerve and the target is left
# alone. It keeps burglary off players who have nothing, which is
# where griefing would otherwise live.
BURGLARY_WORTH_ROBBING = 250

# How long before the same house can be done over again.
BURGLARY_COOLDOWN_SECONDS = 4 * 60 * 60

BURGLARY_JAIL_SECONDS = 30 * 60
BURGLARY_JAIL_CHANCE = 35


class BurglaryError(Exception):
    """Raised when a break-in cannot be attempted."""


@dataclass(frozen=True)
class BurglaryOdds:
    chance: int
    security: int
    tool_bonus: int
    tools: tuple


def home_security(residence_key):
    """How much this address takes off a burglar's chances."""
    return HOME_SECURITY.get(residence_key, 0)


def burglary_tools(inventory):
    """The break-in kit being carried, capped the same way crimes cap it."""
    return tuple(
        tool for tool in usable_tools(inventory, "brixton_warehouse")
        if tool.key in BURGLARY_TOOLS
    )


def odds_against(inventory, residence_key):
    """The burglar's chance against this address, and why."""
    carried = tuple(
        key for key in BURGLARY_TOOLS
        if (inventory or {}).get(key, 0) > 0
    )[:2]
    bonus = len(carried) * TOOL_SUCCESS_BONUS
    security = home_security(residence_key)

    return BurglaryOdds(
        chance=max(5, min(95, BURGLARY_BASE_CHANCE - security + bonus)),
        security=security,
        tool_bonus=bonus,
        tools=carried,
    )


def takings(safe_balance):
    """What a successful break-in walks away with.

    Never the lot. Somebody who comes home to an empty safe stops
    playing; somebody who comes home to a dent goes and does something
    about it.
    """
    if safe_balance < BURGLARY_WORTH_ROBBING:
        return 0

    return max(
        1,
        min(
            BURGLARY_TAKE_CAP,
            safe_balance * BURGLARY_TAKE_PERCENT // 100,
        ),
    )


def worth_robbing(safe_balance):
    return safe_balance >= BURGLARY_WORTH_ROBBING
