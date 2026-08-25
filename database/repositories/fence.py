"""Selling to the black market.

The rules live in `game.economy.fence`; this runs them inside a
transaction so two tabs cannot sell the same item twice.

Mirrors the blocking rules `game.shop.purchase` already enforces --
right district, not travelling, not in jail or hospital -- because a
fence is a place you have to physically get to.
"""

import sqlite3

from database.core.connection import get_connection
from game.economy.fence import fence_price, get_fence
from game.inventory import ITEMS_BY_KEY


MAXIMUM_SALE_QUANTITY = 20


class FenceError(Exception):
    """Raised when a sale cannot go through."""


def sell_to_fence(user_id, district, item_key, quantity):
    fence = get_fence(district)

    if fence is None:
        raise FenceError("There is no black market in this district.")

    definition = ITEMS_BY_KEY.get(item_key)

    if definition is None:
        raise FenceError("Nobody deals in that.")

    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or quantity < 1
    ):
        raise FenceError("Choose how many to sell.")

    if quantity > MAXIMUM_SALE_QUANTITY:
        raise FenceError(
            f"You can sell at most {MAXIMUM_SALE_QUANTITY} at a time."
        )

    unit_price = fence_price(definition, district)
    payout = unit_price * quantity
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        player = connection.execute(
            """
            SELECT id, current_district, travel_destination,
                   jail_until, hospital_until
            FROM players
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if player is None:
            raise FenceError("Player not found.")

        (
            player_id,
            player_district,
            travelling,
            jail_until,
            hospital_until,
        ) = player

        if player_district != district:
            raise FenceError("You are not in that district.")
        if travelling:
            raise FenceError("You cannot deal while travelling.")
        if jail_until or hospital_until:
            raise FenceError("You cannot deal while restricted.")

        owned = connection.execute(
            """
            SELECT quantity
            FROM player_inventory
            WHERE player_id = ? AND item_key = ?
            """,
            (player_id, item_key),
        ).fetchone()

        if owned is None or owned[0] < quantity:
            raise FenceError(f"You do not have that many {definition.name}.")

        remaining = owned[0] - quantity

        # The inventory row has a quantity > 0 constraint, so an emptied
        # stack is deleted rather than zeroed.
        if remaining:
            connection.execute(
                """
                UPDATE player_inventory
                SET quantity = ?
                WHERE player_id = ? AND item_key = ?
                """,
                (remaining, player_id, item_key),
            )
        else:
            connection.execute(
                """
                DELETE FROM player_inventory
                WHERE player_id = ? AND item_key = ?
                """,
                (player_id, item_key),
            )

        connection.execute(
            "UPDATE players SET money = money + ? WHERE id = ?",
            (payout, player_id),
        )
        connection.execute(
            """
            INSERT INTO fence_transactions (
                player_id, fence_key, item_key,
                quantity, unit_price, payout
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                player_id,
                fence.key,
                item_key,
                quantity,
                unit_price,
                payout,
            ),
        )
        connection.commit()

        return {
            "item": definition,
            "quantity": quantity,
            "unit_price": unit_price,
            "payout": payout,
            "fence": fence,
        }
    except (FenceError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()
