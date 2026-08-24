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


DISTRICT_SHOPS = {
    "camden": {
        "key": "camden_corner",
        "name": "Camden Corner Shop",
        "strapline": "Everyday supplies from behind the counter.",
        "items": (
            ShopItem("energy_drink", "Energy Drink", "Restores up to 20 energy.", 75, 10, 30),
            ShopItem("first_aid_kit", "First Aid Kit", "Restores up to 25 health.", 120, 6, 18),
            ShopItem("lockpick", "Basic Lockpick", "Useful for selected crime opportunities.", 180, 3, 12),
        ),
    },
    "brixton": {
        "key": "brixton_trade",
        "name": "Brixton Trade Counter",
        "strapline": "Hard-wearing gear and back-room supplies.",
        "items": (
            ShopItem("kitchen_knife", "Kitchen Knife", "A basic close-range weapon.", 260, 2, 7),
            ShopItem("padded_jacket", "Padded Jacket", "Basic protection for a new player.", 420, 2, 6),
            ShopItem("energy_drink", "Energy Drink", "Restores up to 20 energy.", 85, 8, 22),
        ),
    },
    "soho": {
        "key": "soho_night",
        "name": "Soho Night Pharmacy",
        "strapline": "Late-night recovery and discreet tools.",
        "items": (
            ShopItem("first_aid_kit", "First Aid Kit", "Restores up to 25 health.", 135, 8, 20),
            ShopItem("energy_drink", "Energy Drink", "Restores up to 20 energy.", 95, 12, 28),
            ShopItem("lockpick", "Basic Lockpick", "Useful for selected crime opportunities.", 210, 5, 15),
        ),
    },
}


class ShopError(Exception):
    """Raised when a shop action cannot be completed."""


def _utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_shop(district):
    shop = DISTRICT_SHOPS.get(district)
    if shop is None:
        raise ShopError("There is no shop in this district.")
    return shop


def _ensure_stock(conn, shop, now=None, rng=None):
    now = now or _utcnow()
    rng = rng or random.SystemRandom()
    row = conn.execute(
        "SELECT restock_at FROM shop_cycles WHERE shop_key = ?",
        (shop["key"],),
    ).fetchone()

    if row is not None and _parse_utc(row[0]) > now:
        return _parse_utc(row[0])

    restock_at = now + timedelta(hours=RESTOCK_HOURS)
    conn.execute(
        """
        INSERT INTO shop_cycles (shop_key, restock_at)
        VALUES (?, ?)
        ON CONFLICT(shop_key) DO UPDATE SET restock_at = excluded.restock_at
        """,
        (shop["key"], _format_utc(restock_at)),
    )
    for item in shop["items"]:
        quantity = rng.randint(item.minimum_stock, item.maximum_stock)
        conn.execute(
            """
            INSERT INTO shop_stock (shop_key, item_key, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(shop_key, item_key)
            DO UPDATE SET quantity = excluded.quantity
            """,
            (shop["key"], item.item_key, quantity),
        )
    return restock_at


def get_district_shop(district):
    shop = _require_shop(district)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        restock_at = _ensure_stock(conn, shop)
        rows = dict(conn.execute(
            "SELECT item_key, quantity FROM shop_stock WHERE shop_key = ?",
            (shop["key"],),
        ).fetchall())
        conn.commit()
    finally:
        conn.close()

    return {
        "key": shop["key"],
        "name": shop["name"],
        "district": district,
        "strapline": shop["strapline"],
        "restock_at": _format_utc(restock_at),
        "items": tuple({
            "key": item.item_key,
            "name": item.name,
            "description": item.description,
            "price": item.price,
            "stock": rows.get(item.item_key, 0),
        } for item in shop["items"]),
    }


def purchase(user_id, district, item_key, quantity):
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ShopError("Choose a valid quantity.")
    if quantity > 20:
        raise ShopError("You can buy a maximum of 20 at once.")

    shop = _require_shop(district)
    offer = next(
        (item for item in shop["items"] if item.item_key == item_key),
        None,
    )
    if offer is None:
        raise ShopError("That item is not sold in this district.")
    definition = ITEMS_BY_KEY[item_key]
    total = offer.price * quantity
    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_stock(conn, shop)
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
        player_id, money, player_district, travelling, jail_until, hospital_until = player
        if player_district != district:
            raise ShopError("You must be in the shop's district.")
        if travelling:
            raise ShopError("You cannot shop while travelling.")
        if jail_until or hospital_until:
            raise ShopError("You cannot shop while restricted.")
        stock_row = conn.execute(
            """
            SELECT quantity FROM shop_stock
            WHERE shop_key = ? AND item_key = ?
            """,
            (shop["key"], item_key),
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
            WHERE shop_key = ? AND item_key = ?
            """,
            (quantity, shop["key"], item_key),
        )
        conn.execute(
            """
            INSERT INTO shop_transactions
                (player_id, shop_key, item_key, quantity, unit_price, total_price)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (player_id, shop["key"], item_key, quantity, offer.price, total),
        )
        conn.commit()
        return {"item": offer, "quantity": quantity, "total": total}
    except (ShopError, sqlite3.Error):
        conn.rollback()
        raise
    finally:
        conn.close()
