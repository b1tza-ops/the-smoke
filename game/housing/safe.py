"""Cash kept at home, and what it costs to keep it there.

The bank in this game is free, unlimited, instant and reachable from
every page. A safe that merely protected money would therefore be a
capacity-limited worse bank, and nobody would ever put a pound in it --
which would also leave burglary with nothing to steal. Dead content
twice over.

So the safe is not the safe option. It is the one that pays.

  Bank     untouchable, earns nothing
  Safe     earns interest, can be burgled by another player
  Pockets  earns nothing, taken when you lose a fight

That is the whole design: three places to put money, and the only one
that grows is the one somebody can come and take. Rent is the sink, the
safe is the hedge against it, and a burglar is the reason the hedge is
not free money.
"""

from game.housing.service import get_residence


class SafeError(Exception):
    """Raised when money cannot move in or out of the safe."""


# Per day, on whatever is sitting in the safe. Deliberately smaller than
# rent at every rung: a full penthouse safe earns about £250 a day
# against £550 of rent, so keeping cash at home softens the sink without
# turning the top of the housing ladder into something that pays for
# itself.
SAFE_DAILY_INTEREST_RATE = 0.0025

# Interest is worked out from elapsed time when the safe is next
# touched, like every other clock in this game. Capped so somebody who
# stops playing for a year does not come back to a fortune.
MAXIMUM_INTEREST_DAYS = 30


def safe_capacity(residence):
    """How much this home will hold.

    The tent holds £100, which is not a safe so much as a biscuit tin --
    enough that the feature is visible from the first hour, not enough
    that anybody would bother breaking in for it.
    """
    if residence is None:
        return 0

    return residence.safe_cash_capacity


def capacity_for(residence_key):
    return safe_capacity(get_residence(residence_key))


def room_left(residence_key, balance):
    return max(0, capacity_for(residence_key) - max(0, balance))


def interest_earned(balance, elapsed):
    """What a balance has earned over an elapsed period.

    Whole pounds only, rounded down. A balance too small to earn a
    pound a month earns nothing, which is the honest answer rather than
    a rounding gift.
    """
    if balance <= 0 or elapsed.total_seconds() <= 0:
        return 0

    days = min(elapsed.total_seconds() / 86_400, MAXIMUM_INTEREST_DAYS)

    return int(balance * SAFE_DAILY_INTEREST_RATE * days)
