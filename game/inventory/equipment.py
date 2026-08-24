from dataclasses import dataclass

from database.core.connection import get_connection
from game.inventory.items import get_item


EQUIPMENT_SLOTS = ("weapon", "armour")


class EquipmentError(Exception):
    """Base exception for loadout actions."""


class ItemNotOwnedError(EquipmentError):
    """Raised when a player tries to equip an unowned item."""


class ItemNotEquippableError(EquipmentError):
    """Raised when an item has no equipment slot."""


class EmptyEquipmentSlotError(EquipmentError):
    """Raised when an equipment slot is already empty."""


@dataclass(frozen=True)
class EquipmentSummary:
    items: dict
    strength_bonus: int
    defence_bonus: int


def get_equipment(player_id):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT slot, item_key
            FROM player_equipment
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchall()
    finally:
        connection.close()

    return {
        slot: get_item(item_key)
        for slot, item_key in rows
        if get_item(item_key) is not None
    }


def get_equipment_summary(player_id):
    items = get_equipment(player_id)
    return EquipmentSummary(
        items=items,
        strength_bonus=sum(
            item.strength_bonus for item in items.values()
        ),
        defence_bonus=sum(
            item.defence_bonus for item in items.values()
        ),
    )


def equip_item(player_id, item_key):
    item = get_item(item_key)
    if item is None:
        raise ItemNotEquippableError("Item does not exist.")
    if item.equipment_slot not in EQUIPMENT_SLOTS:
        raise ItemNotEquippableError(
            f"{item.name} cannot be equipped."
        )

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        owned = connection.execute(
            """
            SELECT quantity
            FROM player_inventory
            WHERE player_id = ? AND item_key = ?
            """,
            (player_id, item.key),
        ).fetchone()
        if owned is None or owned[0] < 1:
            raise ItemNotOwnedError(
                f"You do not own {item.name}."
            )

        connection.execute(
            """
            INSERT INTO player_equipment (
                player_id,
                slot,
                item_key
            )
            VALUES (?, ?, ?)
            ON CONFLICT(player_id, slot)
            DO UPDATE SET item_key = excluded.item_key
            """,
            (player_id, item.equipment_slot, item.key),
        )
        connection.commit()
        return item
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def unequip_item(player_id, slot):
    if slot not in EQUIPMENT_SLOTS:
        raise EmptyEquipmentSlotError(
            "Equipment slot does not exist."
        )

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            DELETE FROM player_equipment
            WHERE player_id = ? AND slot = ?
            """,
            (player_id, slot),
        )
        if cursor.rowcount == 0:
            raise EmptyEquipmentSlotError(
                f"Your {slot} slot is already empty."
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
