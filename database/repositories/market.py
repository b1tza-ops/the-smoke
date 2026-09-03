"""Storage for the global item market.

Every operation is one `BEGIN IMMEDIATE` transaction, because each moves
an item and money between two players and a half-applied trade would
duplicate or destroy either.

Listing escrows the items out of the seller's inventory onto the listing
row. That is what makes double-selling impossible: once listed, the
seller is no longer carrying them.
"""

import sqlite3

from database.core.connection import get_connection
from database.repositories.agents import refuse_if_sealed
from game.economy.market import (
    commission_on,
    seller_proceeds,
    validate_listing,
)
from game.inventory import INVENTORY_SLOT_CAPACITY, ITEMS_BY_KEY


class MarketError(Exception):
    """Raised when a listing or a purchase cannot go through."""


def _player_row(connection, user_id):
    row = connection.execute(
        """
        SELECT id, money, jail_until, hospital_until
        FROM players
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    if row is None:
        raise MarketError("Player not found.")

    return row


def _require_room(connection, player_id, item, quantity):
    """Refuse rather than silently drop items nobody can carry.

    A purchase is deliberate, so it fails loudly -- unlike crime loot,
    which pays cash when there is nowhere to put it.
    """
    owned = connection.execute(
        """
        SELECT quantity
        FROM player_inventory
        WHERE player_id = ? AND item_key = ?
        """,
        (player_id, item.key),
    ).fetchone()
    current = owned[0] if owned else 0

    if current + quantity > item.max_quantity:
        raise MarketError(
            f"You can only carry {item.max_quantity} {item.name}."
        )

    if current == 0:
        slots = connection.execute(
            "SELECT COUNT(*) FROM player_inventory WHERE player_id = ?",
            (player_id,),
        ).fetchone()[0]

        if slots >= INVENTORY_SLOT_CAPACITY:
            raise MarketError("Your inventory is full.")


def _give(connection, player_id, item_key, quantity):
    connection.execute(
        """
        INSERT INTO player_inventory (player_id, item_key, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(player_id, item_key)
        DO UPDATE SET quantity = quantity + excluded.quantity
        """,
        (player_id, item_key, quantity),
    )


def create_listing(user_id, item_key, quantity, price_each):
    item = ITEMS_BY_KEY.get(item_key)

    if item is None:
        raise MarketError("Nobody deals in that.")

    try:
        validate_listing(item, quantity, price_each)
    except ValueError as invalid:
        raise MarketError(str(invalid)) from invalid

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, _, jail_until, hospital_until = _player_row(
            connection,
            user_id,
        )
        # Agents play the city, not its economy. A machine listing
        # items would put an endless supply into the human market.
        refuse_if_sealed(connection, "market", player_id)

        if jail_until or hospital_until:
            raise MarketError("You cannot trade while restricted.")

        owned = connection.execute(
            """
            SELECT quantity
            FROM player_inventory
            WHERE player_id = ? AND item_key = ?
            """,
            (player_id, item_key),
        ).fetchone()

        if owned is None or owned[0] < quantity:
            raise MarketError(f"You do not have that many {item.name}.")

        remaining = owned[0] - quantity

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

        cursor = connection.execute(
            """
            INSERT INTO market_listings (
                seller_player_id, item_key, quantity, price_each
            )
            VALUES (?, ?, ?, ?)
            """,
            (player_id, item_key, quantity, price_each),
        )
        connection.commit()

        return {
            "id": cursor.lastrowid,
            "item": item,
            "quantity": quantity,
            "price_each": price_each,
            "total": price_each * quantity,
        }
    except (MarketError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


def buy_listing(user_id, listing_id):
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        buyer_id, money, jail_until, hospital_until = _player_row(
            connection,
            user_id,
        )
        refuse_if_sealed(connection, "market", buyer_id)

        if jail_until or hospital_until:
            raise MarketError("You cannot trade while restricted.")

        listing = connection.execute(
            """
            SELECT seller_player_id, item_key, quantity, price_each, status
            FROM market_listings
            WHERE id = ?
            """,
            (listing_id,),
        ).fetchone()

        if listing is None:
            raise MarketError("That listing does not exist.")

        seller_id, item_key, quantity, price_each, status = listing

        if status != "open":
            raise MarketError("That listing is already gone.")

        if seller_id == buyer_id:
            raise MarketError("You cannot buy your own listing.")

        item = ITEMS_BY_KEY[item_key]
        total = price_each * quantity

        if money < total:
            raise MarketError("You do not have enough cash.")

        _require_room(connection, buyer_id, item, quantity)

        commission = commission_on(total)
        connection.execute(
            "UPDATE players SET money = money - ? WHERE id = ?",
            (total, buyer_id),
        )
        connection.execute(
            "UPDATE players SET money = money + ? WHERE id = ?",
            (seller_proceeds(total), seller_id),
        )
        _give(connection, buyer_id, item_key, quantity)

        # Guarded on status so two simultaneous buyers cannot both win.
        closed = connection.execute(
            """
            UPDATE market_listings
            SET status = 'sold',
                buyer_player_id = ?,
                commission = ?,
                closed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'open'
            """,
            (buyer_id, commission, listing_id),
        )

        if closed.rowcount != 1:
            raise MarketError("That listing is already gone.")

        connection.commit()

        return {
            "item": item,
            "quantity": quantity,
            "price_each": price_each,
            "total": total,
            "commission": commission,
        }
    except (MarketError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


def cancel_listing(user_id, listing_id):
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, _, jail_until, hospital_until = _player_row(
            connection,
            user_id,
        )

        if jail_until or hospital_until:
            raise MarketError("You cannot trade while restricted.")

        listing = connection.execute(
            """
            SELECT seller_player_id, item_key, quantity, status
            FROM market_listings
            WHERE id = ?
            """,
            (listing_id,),
        ).fetchone()

        if listing is None:
            raise MarketError("That listing does not exist.")

        seller_id, item_key, quantity, status = listing

        if seller_id != player_id:
            raise MarketError("That is not your listing.")

        if status != "open":
            raise MarketError("That listing is already closed.")

        item = ITEMS_BY_KEY[item_key]
        # The listing stays open if the items cannot come back, rather
        # than closing and losing them.
        _require_room(connection, player_id, item, quantity)
        _give(connection, player_id, item_key, quantity)

        connection.execute(
            """
            UPDATE market_listings
            SET status = 'cancelled', closed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'open'
            """,
            (listing_id,),
        )
        connection.commit()

        return {"item": item, "quantity": quantity}
    except (MarketError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


def get_open_listings(user_id=None):
    """Every open listing, cheapest per unit first."""
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                listing.id,
                listing.item_key,
                listing.quantity,
                listing.price_each,
                listing.created_at,
                player.id,
                player.name,
                player.user_id
            FROM market_listings AS listing
            JOIN players AS player
                ON player.id = listing.seller_player_id
            WHERE listing.status = 'open'
            ORDER BY listing.price_each ASC, listing.created_at ASC
            """
        ).fetchall()

        return tuple(
            {
                "id": row[0],
                "item": ITEMS_BY_KEY[row[1]],
                "quantity": row[2],
                "price_each": row[3],
                "total": row[3] * row[2],
                "created_at": row[4],
                "seller_name": row[6],
                "is_own": user_id is not None and row[7] == user_id,
            }
            for row in rows
            if row[1] in ITEMS_BY_KEY
        )
    finally:
        connection.close()
