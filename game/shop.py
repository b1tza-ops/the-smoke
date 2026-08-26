"""Shared district shop stock and transactional purchases."""

import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from database.core.connection import get_connection
from game.inventory import ITEMS_BY_KEY


RESTOCK_HOURS = 24

# Per-transaction cap. Each item's own max_quantity is checked as well
# and is lower for everything except ammunition, which is bought by the
# hundred rather than the handful.
MAXIMUM_PURCHASE_QUANTITY = 200


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
            ShopItem("bottled_water", "Bottled Water", "Restores up to 10 energy.", 25, 18, 45),
            ShopItem("screwdriver", "Heavy Screwdriver", "A common improvised weapon.", 140, 3, 10),
            ShopItem("work_boots", "Reinforced Work Boots", "Modest everyday protection.", 300, 2, 7),
            ShopItem("bandage_roll", "Bandage Roll", "Restores up to 10 health.", 45, 12, 30),
            ShopItem("protein_bar", "Protein Bar", "Restores up to 8 energy.", 35, 12, 30),
            ShopItem("duct_tape", "Duct Tape", "Useful for improvised plans.", 90, 5, 16),
            ShopItem("hard_hat", "Construction Hard Hat", "Basic head protection.", 380, 2, 7),
            ShopItem("trainers", "Street Trainers", "Light protective footwear.", 220, 3, 9),
            ShopItem("fish_and_chips", "Fish and Chips", "Restores up to 25 happiness.", 55, 10, 25),
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
            ShopItem("claw_hammer", "Claw Hammer", "A solid improvised weapon.", 340, 2, 7),
            ShopItem("crowbar", "Crowbar", "Heavy steel with serious leverage.", 520, 2, 6),
            ShopItem("baseball_bat", "Baseball Bat", "A weighty bat with a taped grip.", 700, 1, 5),
            ShopItem("machete", "Machete", "A formidable heavy blade.", 1450, 1, 3),
            ShopItem("heavy_coat", "Heavy Coat", "Thick street protection.", 900, 1, 5),
            ShopItem("stab_vest", "Protective Vest", "Serious protection for dangerous streets.", 1800, 1, 3),
            ShopItem("police_baton", "Police Baton", "A balanced close-range weapon.", 620, 2, 6),
            ShopItem("tire_iron", "Tyre Iron", "Compact steel with a punishing swing.", 760, 2, 6),
            ShopItem("hatchet", "Hatchet", "A short, heavy chopping weapon.", 980, 1, 5),
            ShopItem("denim_jacket", "Reinforced Denim Jacket", "Street clothing with sewn-in padding.", 720, 2, 6),
            ShopItem("combat_gloves", "Combat Gloves", "Reinforced hand protection.", 520, 2, 7),
            ShopItem("cargo_trousers", "Padded Cargo Trousers", "Hard-wearing leg protection.", 650, 2, 6),
            ShopItem("tactical_boots", "Tactical Boots", "Heavy footwear for dangerous work.", 940, 1, 5),
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
            ShopItem("bottled_water", "Bottled Water", "Restores up to 10 energy.", 35, 16, 38),
            ShopItem("leather_gloves", "Leather Gloves", "Light hand protection.", 240, 3, 9),
            ShopItem("motorcycle_helmet", "Motorcycle Helmet", "Strong protection with a dark visor.", 780, 1, 5),
            ShopItem("sports_drink", "Sports Drink", "Restores up to 30 energy.", 140, 6, 18),
            ShopItem("painkillers", "Painkillers", "Restores up to 15 health.", 80, 8, 22),
            ShopItem("glass_cutter", "Glass Cutter", "A precise tool for quiet entry.", 340, 3, 10),
            ShopItem("burner_phone", "Burner Phone", "A disposable phone for discreet work.", 260, 3, 9),
            ShopItem("bolt_cutters", "Bolt Cutters", "Heavy cutters used in selected crimes.", 460, 2, 7),
            ShopItem("survival_knife", "Survival Knife", "A stronger secondary blade.", 880, 1, 5),
            ShopItem("reinforced_jeans", "Reinforced Jeans", "Protective fibres under street denim.", 1100, 1, 4),
            ShopItem("riot_helmet", "Riot Helmet", "Reinforced full-face protection.", 1650, 1, 3),
            ShopItem("fish_and_chips", "Fish and Chips", "Restores up to 25 happiness.", 65, 8, 20),
        ),
    },
    "shoreditch": {
        "key": "shoreditch_studio",
        "name": "Shoreditch Studio Supply",
        "strapline": "Gallery tools and gear for people who work nights.",
        "items": (
            ShopItem("glass_cutter", "Glass Cutter", "A precise tool for quiet entry.", 380, 4, 12),
            ShopItem("burner_phone", "Burner Phone", "A disposable phone for discreet work.", 290, 4, 12),
            ShopItem("lockpick", "Basic Lockpick", "Useful for selected crime opportunities.", 230, 4, 14),
            ShopItem("duct_tape", "Duct Tape", "Useful for improvised plans.", 110, 6, 18),
            ShopItem("combat_gloves", "Combat Gloves", "Reinforced knuckles and padded palms.", 640, 2, 7),
            ShopItem("cargo_trousers", "Cargo Trousers", "Hard-wearing legwear with deep pockets.", 480, 2, 8),
            ShopItem("tactical_boots", "Tactical Boots", "Ankle support and a solid sole.", 820, 2, 6),
            ShopItem("denim_jacket", "Denim Jacket", "Everyday cover with a little bite.", 350, 3, 9),
            ShopItem("sports_drink", "Sports Drink", "Restores up to 30 energy.", 150, 8, 22),
            ShopItem("energy_drink", "Energy Drink", "Restores up to 20 energy.", 100, 10, 26),
            ShopItem("painkillers", "Painkillers", "Restores up to 15 health.", 90, 8, 20),
            ShopItem("fish_and_chips", "Fish and Chips", "Restores up to 25 happiness.", 70, 8, 20),
        ),
    },
    "hackney": {
        "key": "hackney_lockup",
        "name": "Hackney Lock-Up",
        "strapline": "Serious kit, sold quietly, cash only.",
        "items": (
            ShopItem("machete", "Machete", "A formidable heavy blade.", 1550, 1, 4),
            ShopItem("survival_knife", "Survival Knife", "A stronger secondary blade.", 940, 2, 6),
            ShopItem("hatchet", "Hatchet", "Short handle, heavy head.", 1050, 1, 5),
            ShopItem("stab_vest", "Protective Vest", "Serious protection for dangerous streets.", 1900, 1, 4),
            ShopItem("riot_helmet", "Riot Helmet", "Reinforced full-face protection.", 1750, 1, 4),
            ShopItem("reinforced_jeans", "Reinforced Jeans", "Protective fibres under street denim.", 1200, 1, 5),
            ShopItem("tactical_boots", "Tactical Boots", "Ankle support and a solid sole.", 860, 2, 6),
            ShopItem("bolt_cutters", "Bolt Cutters", "Heavy cutters used in selected crimes.", 500, 3, 9),
            ShopItem("crowbar", "Crowbar", "Heavy steel with serious leverage.", 570, 2, 7),
            ShopItem("first_aid_kit", "First Aid Kit", "Restores up to 25 health.", 145, 8, 20),
            ShopItem("sports_drink", "Sports Drink", "Restores up to 30 energy.", 155, 6, 18),
            ShopItem("fish_and_chips", "Fish and Chips", "Restores up to 25 happiness.", 75, 8, 18),
        ),
    },
}


# Venues that are not a district's general store. Firearms live here and
# nowhere else, so the bazaar is the one place in London selling them.
SPECIALIST_SHOPS = {
    "kingsland_arms": {
        "key": "kingsland_arms",
        "district": "hackney",
        "name": "Kingsland Arms Bazaar",
        "strapline": "Pistols and rounds, traded under a dead pub's name.",
        "items": (
            ShopItem("derringer_22", "Derringer .22", "A palm-sized two-shot pistol.", 2000, 1, 4),
            ShopItem("converted_blank_pistol", "Converted Blank Pistol", "A starter pistol bored out for live rounds.", 2800, 1, 3),
            ShopItem("snub_nose_38", "Snub-Nose .38", "A short-barrelled revolver that hides easily.", 3600, 1, 3),
            ShopItem("compact_9mm", "Compact 9mm", "A clean semi-automatic, never fired.", 4800, 1, 2),
            ShopItem("ammo_22", ".22 Rounds", "Rimfire rounds, sold loose by the handful.", 10, 200, 400),
            ShopItem("ammo_9mm", "9mm Rounds", "The calibre everything else is chambered for.", 16, 200, 400),
            ShopItem("ammo_38", ".38 Rounds", "Revolver rounds, harder to come by.", 20, 150, 300),
        ),
    },
}


# Every place a player can buy something, keyed by venue rather than by
# district, because Hackney now holds two of them.
VENUES = {
    **{
        shop["key"]: {**shop, "district": district, "kind": "general"}
        for district, shop in DISTRICT_SHOPS.items()
    },
    **{key: {**shop, "kind": "guns"} for key, shop in SPECIALIST_SHOPS.items()},
}

GENERAL_STORE_KEYS = {
    district: shop["key"] for district, shop in DISTRICT_SHOPS.items()
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


def _require_venue(venue_key):
    venue = VENUES.get(venue_key)
    if venue is None:
        raise ShopError("There is no such place in London.")
    return venue


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
    _require_shop(district)
    return get_venue(GENERAL_STORE_KEYS[district])


def get_venue(venue_key):
    shop = _require_venue(venue_key)
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
        "district": shop["district"],
        "kind": shop.get("kind", "general"),
        "strapline": shop["strapline"],
        "restock_at": _format_utc(restock_at),
        "items": tuple({
            "key": item.item_key,
            "name": item.name,
            "description": item.description,
            "category": ITEMS_BY_KEY[item.item_key].category,
            "image_filename": ITEMS_BY_KEY[item.item_key].image_filename,
            "price": item.price,
            "stock": rows.get(item.item_key, 0),
        } for item in shop["items"]),
    }


def purchase(user_id, district, item_key, quantity):
    """Buy from a district's general store."""
    _require_shop(district)
    return purchase_at(
        user_id, GENERAL_STORE_KEYS[district], item_key, quantity
    )


def purchase_at(user_id, venue_key, item_key, quantity):
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ShopError("Choose a valid quantity.")
    if quantity > MAXIMUM_PURCHASE_QUANTITY:
        raise ShopError(
            f"You can buy a maximum of {MAXIMUM_PURCHASE_QUANTITY} at once."
        )

    shop = _require_venue(venue_key)
    district = shop["district"]
    offer = next(
        (item for item in shop["items"] if item.item_key == item_key),
        None,
    )
    if offer is None:
        raise ShopError("That item is not sold here.")
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
