"""Rules for the global item market.

Players list what they are selling and name their own price; anyone can
buy. This is the *ceiling* of the selling economy -- better money than
the black market, but only if somebody turns up to buy. The fence stays
the floor, which is what makes the market safe to add while the player
base is still small: nothing depends on it working.

Pure rules only. `database.repositories.market` runs them in a
transaction.
"""

from game.economy.fence import FENCE_RATE


# Taken from the seller when a listing sells. Money leaves the economy
# on every trade, which matters in a game with few sinks once the gyms
# are bought -- and it makes wash trading between two accounts a way to
# destroy money rather than launder it, so it needs no separate guard.
COMMISSION_RATE = 0.05

MAXIMUM_LISTING_QUANTITY = 20

# Nobody may undercut the fence. Below this a seller should just walk to
# the black market, and it stops £1 listings being used to shuffle items
# between accounts for nothing.
def minimum_price(item):
    return max(1, int(item.value * FENCE_RATE))


def commission_on(total):
    """The house's cut, rounded in the house's favour."""
    return -(-int(total) * int(COMMISSION_RATE * 100) // 100)


def seller_proceeds(total):
    return total - commission_on(total)


def validate_listing(item, quantity, price_each):
    """Raise if a listing would be nonsense. Returns nothing."""
    for value, label in (
        (quantity, "quantity"),
        (price_each, "price"),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Choose a whole {label}.")

    if quantity < 1:
        raise ValueError("Choose how many to list.")

    if quantity > MAXIMUM_LISTING_QUANTITY:
        raise ValueError(
            f"You can list at most {MAXIMUM_LISTING_QUANTITY} at a time."
        )

    if quantity > item.max_quantity:
        raise ValueError(
            f"Nobody can carry {quantity} {item.name}."
        )

    floor = minimum_price(item)

    if price_each < floor:
        raise ValueError(
            f"The black market already pays £{floor:,} for that. "
            "Ask for more."
        )
