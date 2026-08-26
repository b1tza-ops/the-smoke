from dataclasses import dataclass

from database.core.connection import get_connection
from game.inventory.items import AMMO_KEYS, get_item


EQUIPMENT_SLOTS = (
    "primary",
    "secondary",
    "head",
    "body",
    "hands",
    "legs",
    "feet",
)
LEGACY_SLOTS = ("weapon", "armour")


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
    # Equipped firearms with no rounds of their calibre in the player's
    # inventory. They stay in their slot and keep showing on the character
    # sheet, but they contribute nothing above.
    unloaded: tuple = ()
    # The ammunition each loaded firearm will spend on the next fight.
    ammo_in_use: tuple = ()

    @property
    def has_unloaded_weapon(self):
        return bool(self.unloaded)


def _resolved_slot(stored_slot, item):
    if stored_slot in EQUIPMENT_SLOTS:
        return stored_slot
    if stored_slot in LEGACY_SLOTS:
        return item.equipment_slot
    return None


def get_equipment(player_id):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT slot, item_key
            FROM player_equipment
            WHERE player_id = ?
            ORDER BY CASE WHEN slot IN ('weapon', 'armour') THEN 1 ELSE 0 END
            """,
            (player_id,),
        ).fetchall()
    finally:
        connection.close()

    equipped = {}
    for stored_slot, item_key in rows:
        item = get_item(item_key)
        if item is None:
            continue
        slot = _resolved_slot(stored_slot, item)
        if slot in EQUIPMENT_SLOTS and slot not in equipped:
            equipped[slot] = item
    return equipped


def loaded_rounds(player_id):
    """How many rounds of each calibre the player is carrying."""
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT item_key, quantity
            FROM player_inventory
            WHERE player_id = ? AND quantity > 0
            """,
            (player_id,),
        ).fetchall()
    finally:
        connection.close()
    return {
        item_key: quantity
        for item_key, quantity in rows
        if item_key in AMMO_KEYS
    }


def get_equipment_summary(player_id):
    items = get_equipment(player_id)
    rounds = loaded_rounds(player_id)

    unloaded = tuple(
        item for item in items.values()
        if item.ammo_key is not None and rounds.get(item.ammo_key, 0) < 1
    )
    dead_weight = {item.key for item in unloaded}
    ammo_in_use = tuple(sorted({
        item.ammo_key for item in items.values()
        if item.ammo_key is not None and item.key not in dead_weight
    }))

    return EquipmentSummary(
        items=items,
        strength_bonus=sum(
            item.strength_bonus for item in items.values()
            if item.key not in dead_weight
        ),
        defence_bonus=sum(
            item.defence_bonus for item in items.values()
            if item.key not in dead_weight
        ),
        unloaded=unloaded,
        ammo_in_use=ammo_in_use,
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

        legacy_rows = connection.execute(
            """
            SELECT slot, item_key
            FROM player_equipment
            WHERE player_id = ? AND slot IN ('weapon', 'armour')
            """,
            (player_id,),
        ).fetchall()
        for legacy_slot, legacy_key in legacy_rows:
            legacy_item = get_item(legacy_key)
            if (
                legacy_item is not None
                and legacy_item.equipment_slot == item.equipment_slot
            ):
                connection.execute(
                    """
                    DELETE FROM player_equipment
                    WHERE player_id = ? AND slot = ?
                    """,
                    (player_id, legacy_slot),
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
        removed = cursor.rowcount
        if removed == 0:
            legacy_rows = connection.execute(
                """
                SELECT slot, item_key
                FROM player_equipment
                WHERE player_id = ? AND slot IN ('weapon', 'armour')
                """,
                (player_id,),
            ).fetchall()
            for legacy_slot, item_key in legacy_rows:
                item = get_item(item_key)
                if item is not None and item.equipment_slot == slot:
                    connection.execute(
                        """
                        DELETE FROM player_equipment
                        WHERE player_id = ? AND slot = ?
                        """,
                        (player_id, legacy_slot),
                    )
                    removed += 1
        if removed == 0:
            raise EmptyEquipmentSlotError(
                f"Your {slot} slot is already empty."
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
