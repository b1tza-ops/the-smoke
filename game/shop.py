"""Shared district shop stock and transactional purchases."""

import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from database.core.connection import get_connection
from game.inventory import ITEMS_BY_KEY


RESTOCK_HOURS = 24


@dataclass(frozen=True)
class ShopItem:
    item_key: str
    name: str
    description: str
    price: int
    minimum_stock: int
    maximum_stock: int


CAMDEN_CORNER_SHOP = (
    ShopItem("energy_drink", "Energy Drink", "Restores up to 20 energy.", 75, 10, 30),
    ShopItem("first_aid_kit", "First Aid Kit", "Restores up to 25 health.", 120, 6, 18),
    ShopItem("lockpick", "Basic Lockpick", "Useful for selected crime opportunities.", 180, 3, 12),
)
SHOP_ITEMS = {item.item_key: item for item in CAMDEN_CORNER_SHOP}


class ShopError(Exception):
    """Raised when a shop action cannot be completed."""


def _utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_stock(conn, now=None, rng=None):
    now = now or _utcnow()
    rng = rng or random.SystemRandom()
    row = conn.execute(
        "SELECT restock_at FROM shop_cycles WHERE shop_key = 'camden_corner'"
    ).fetchone()

    if row is not None and _parse_utc(row[0]) > now:
        return _parse_utc(row[0])

    restock_at = now + timedelta(hours=RESTOCK_HOURS)
    conn.execute(
        """
        INSERT INTO shop_cycles (shop_key, restock_at)
        VALUES ('camden_corner', ?)
        ON CONFLICT(shop_key) DO UPDATE SET restock_at = excluded.restock_at
        """,
        (_format_utc(restock_at),),
    )
    for item in CAMDEN_CORNER_SHOP:
        quantity = rng.randint(item.minimum_stock, item.maximum_stock)
        conn.execute(
            """
            INSERT INTO shop_stock (shop_key, item_key, quantity)
            VALUES ('camden_corner', ?, ?)
            ON CONFLICT(shop_key, item_key)
            DO UPDATE SET quantity = excluded.quantity
            """,
            (item.item_key, quantity),
        )
    return restock_at


def get_camden_shop():
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        restock_at = _ensure_stock(conn)
        rows = dict(conn.execute(
            "SELECT item_key, quantity FROM shop_stock WHERE shop_key = 'camden_corner'"
        ).fetchall())
        conn.commit()
    finally:
        conn.close()

    return {
        "name": "Camden Corner Shop",
        "restock_at": _format_utc(restock_at),
        "items": tuple({
            "key": item.item_key,
            "name": item.name,
            "description": item.description,
            "price": item.price,
            "stock": rows.get(item.item_key, 0),
        } for item in CAMDEN_CORNER_SHOP),
    }


def purchase(user_id, item_key, quantity):
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ShopError("Choose a valid quantity.")
    if quantity > 20:
        raise ShopError("You can buy a maximum of 20 at once.")

    offer = SHOP_ITEMS.get(item_key)
    if offer is None:
        raise ShopError("That item is not sold here.")
    definition = ITEMS_BY_KEY[item_key]
    total = offer.price * quantity
    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_stock(conn)
        player = conn.execute(
            """
            SELECT id, money, current_district, travel_destination,
                   jail_until, hospital_until
            FROM players WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if player is None:
            raise ShopError("Player not found.")
        player_id, money, district, travelling, jail_until, hospital_until = player
        if district != "camden" or travelling:
            raise ShopError("You must be in Camden to use this shop.")
        if jail_until or hospital_until:
            raise ShopError("You cannot shop while restricted.")
        stock_row = conn.execute(
            """
            SELECT quantity FROM shop_stock
            WHERE shop_key = 'camden_corner' AND item_key = ?
            """,
            (item_key,),
        ).fetchone()
        available = stock_row[0] if stock_row else 0
        if quantity > available:
            raise ShopError("The shop does not have that many left.")
        if total > money:
            raise ShopError("You do not have enough cash.")

        owned_row = conn.execute(
            "SELECT quantity FROM player_inventory WHERE player_id = ? AND item_key = ?",
            (player_id, item_key),
        ).fetchone()
        owned = owned_row[0] if owned_row else 0
        if owned + quantity > definition.max_quantity:
            raise ShopError(
                f"You can carry a maximum of {definition.max_quantity} {definition.name}."
            )

        conn.execute("UPDATE players SET money = money - ? WHERE id = ?", (total, player_id))
        conn.execute(
            """
            INSERT INTO player_inventory (player_id, item_key, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(player_id, item_key)
            DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (player_id, item_key, quantity),
        )
        conn.execute(
            """
            UPDATE shop_stock SET quantity = quantity - ?
            WHERE shop_key = 'camden_corner' AND item_key = ?
            """,
            (quantity, item_key),
        )
        conn.execute(
            """
            INSERT INTO shop_transactions
                (player_id, shop_key, item_key, quantity, unit_price, total_price)
            VALUES (?, 'camden_corner', ?, ?, ?, ?)
            """,
            (player_id, item_key, quantity, offer.price, total),
        )
        conn.commit()
        return {"item": offer, "quantity": quantity, "total": total}
    except (ShopError, sqlite3.Error):
        conn.rollback()
        raise
    finally:
        conn.close()
