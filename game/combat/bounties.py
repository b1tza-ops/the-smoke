"""Money on somebody's head.

The Smoke has a lot of content and, until now, very little reason to
care that anybody else exists. You fight strangers for rating, you rob
a safe for cash, and then you go back to the crime list. Nothing you do
gives another player a reason to think about *you*.

A bounty is the cheapest fix for that, because it works with almost
nobody online: you pay to put a price on a name, the price sits on the
board until somebody collects it, and neither of you has to be awake at
the same time.

It also gives the aftermath screen a real decision. Beating somebody
already offers Leave, Mug and Hospitalise, and Mug always won -- it
paid, and the other two did not. A bounty is collected by hospitalising
the target, so the choice becomes *their pockets or their price*, and
which one is bigger changes fight to fight.

Pure rules only. `database.repositories.bounties` runs them inside a
transaction.
"""


class BountyError(Exception):
    """Raised when a bounty cannot be posted or collected."""


# Below this the board is noise. It is about an hour of a new player's
# crime income, which is roughly what it should cost to be taken
# seriously.
BOUNTY_MINIMUM = 500

# Per bounty, not per head: several people can stack prices on the same
# target and every one of them pays out. The cap only stops one
# fat-fingered zero turning a player into a permanent target.
BOUNTY_MAXIMUM = 250_000

# The fixer's cut, paid on top of the stake and gone for good. This is
# the sink -- posting £10,000 costs £11,000 -- and it is also what makes
# passing money between two accounts through the board a lossy way to do
# something the item market already does for 5%.
BOUNTY_FEE_PERCENT = 10

# An unclaimed bounty is not a life sentence. After a week it lapses and
# the stake goes back to whoever posted it; the fee does not.
BOUNTY_LIFETIME_DAYS = 7
BOUNTY_LIFETIME_SECONDS = BOUNTY_LIFETIME_DAYS * 24 * 60 * 60

# The same window fights and burglaries use. Somebody's first three days
# should not be spent with a price on their head.
NEW_PLAYER_PROTECTION_HOURS = 72

# How many open bounties one player may have running at once. Without
# it, a rich player can paper the whole board and nobody else's bounty
# is worth reading.
MAXIMUM_OPEN_BOUNTIES = 10


def posting_fee(stake):
    """The fixer's cut, rounded in the fixer's favour."""
    return -(-int(stake) * BOUNTY_FEE_PERCENT // 100)


def total_cost(stake):
    """What leaves the poster's wallet: the stake plus the cut."""
    return int(stake) + posting_fee(stake)


def validate_stake(stake):
    """Raise unless this is a sum somebody may put on a head."""
    if isinstance(stake, bool) or not isinstance(stake, int):
        raise BountyError("Name a whole number of pounds.")

    if stake < BOUNTY_MINIMUM:
        raise BountyError(
            f"Nobody gets out of bed for less than "
            f"£{BOUNTY_MINIMUM:,}."
        )

    if stake > BOUNTY_MAXIMUM:
        raise BountyError(
            f"£{BOUNTY_MAXIMUM:,} is the most one bounty can carry. "
            "Post another if you mean it."
        )


def seconds_left(expires_at, now):
    """How long an open bounty has left to run, never below zero."""
    return max(0, int((expires_at - now).total_seconds()))


def collectable(bounties, claimer_id):
    """Split open bounties into the ones this winner may actually take.

    You cannot collect your own money. Skipping those rather than
    refusing the whole payout matters: otherwise posting £500 on a
    target would make everybody else's bounty on them uncollectable by
    you, which is a grief tactic rather than a rule.

    Each bounty is anything with `id`, `poster_id` and `amount`.
    """
    payable = tuple(
        bounty for bounty in bounties
        if bounty["poster_id"] != claimer_id
    )
    skipped = tuple(
        bounty for bounty in bounties
        if bounty["poster_id"] == claimer_id
    )

    return payable, skipped

