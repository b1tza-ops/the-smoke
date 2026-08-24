from dataclasses import dataclass

from game.inventory.items import (
    ITEMS,
    ItemDefinition,
    get_item,
)


INVENTORY_SLOT_CAPACITY = 20


class InventoryError(Exception):
    """Base exception for inventory actions."""


class UnknownItemError(InventoryError):
    """Raised when an item key is not recognised."""


class InvalidQuantityError(InventoryError):
    """Raised when quantity is not a positive integer."""


class ItemLimitError(InventoryError):
    """Raised when an item's stack limit would be exceeded."""


class InsufficientItemError(InventoryError):
    """Raised when the inventory lacks the requested quantity."""


class InventoryFullError(InventoryError):
    """Raised when no additional item slot is available."""


class ItemNotUsableError(InventoryError):
    """Raised when an item has no consumable effect."""


class ResourceAlreadyFullError(InventoryError):
    """Raised when a consumable cannot improve its resource."""


@dataclass(frozen=True)
class InventoryChangeResult:
    item_key: str
    quantity_changed: int
    quantity_after: int


@dataclass(frozen=True)
class ItemUseResult:
    item_key: str
    effect_key: str
    amount_restored: int
    quantity_after: int


def add_item(player, item_key, quantity=1):
    item = _require_item(item_key)
    _validate_quantity(quantity)
    inventory = _inventory_for(player)
    current_quantity = inventory.get(item.key, 0)

    if (
        current_quantity == 0
        and len(inventory) >= INVENTORY_SLOT_CAPACITY
    ):
        raise InventoryFullError(
            "Inventory has no free item slots."
        )

    new_quantity = current_quantity + quantity

    if new_quantity > item.max_quantity:
        raise ItemLimitError(
            f"{item.name} is limited to "
            f"{item.max_quantity}."
        )

    if not item.stackable and new_quantity > 1:
        raise ItemLimitError(
            f"{item.name} is not stackable."
        )

    inventory[item.key] = new_quantity

    return InventoryChangeResult(
        item_key=item.key,
        quantity_changed=quantity,
        quantity_after=new_quantity,
    )


def remove_item(player, item_key, quantity=1):
    item = _require_item(item_key)
    _validate_quantity(quantity)
    inventory = _inventory_for(player)
    current_quantity = inventory.get(item.key, 0)

    if quantity > current_quantity:
        raise InsufficientItemError(
            f"Not enough {item.name} items."
        )

    new_quantity = current_quantity - quantity

    if new_quantity == 0:
        inventory.pop(item.key)
    else:
        inventory[item.key] = new_quantity

    return InventoryChangeResult(
        item_key=item.key,
        quantity_changed=-quantity,
        quantity_after=new_quantity,
    )


def use_item(player, item_key):
    item = _require_item(item_key)

    if item.effect_key is None:
        raise ItemNotUsableError(
            f"{item.name} cannot be consumed."
        )

    inventory = _inventory_for(player)

    if inventory.get(item.key, 0) < 1:
        raise InsufficientItemError(
            f"You do not have {item.name}."
        )

    current_value, maximum_value = _resource_values(
        player,
        item.effect_key,
    )

    if current_value >= maximum_value:
        raise ResourceAlreadyFullError(
            f"{item.effect_key.title()} is already full."
        )

    new_value = min(
        maximum_value,
        current_value + item.effect_amount,
    )
    restored = new_value - current_value
    setattr(
        player,
        item.effect_key,
        new_value,
    )
    change = remove_item(
        player,
        item.key,
        quantity=1,
    )

    return ItemUseResult(
        item_key=item.key,
        effect_key=item.effect_key,
        amount_restored=restored,
        quantity_after=change.quantity_after,
    )


def inventory_menu(player):
    while True:
        inventory = _inventory_for(player)

        print("\n===== INVENTORY =====")
        print(
            "Capacity:",
            f"{len(inventory)}/{INVENTORY_SLOT_CAPACITY}",
        )

        if not inventory:
            print("Your inventory is empty.")
            input("\nPress Enter to go back.")
            return

        entries = []

        for item in ITEMS:
            quantity = inventory.get(item.key, 0)

            if quantity == 0:
                continue

            entries.append(item)
            print(
                f"{len(entries)}. [{item.category.title()}] "
                f"{item.name} x{quantity}"
            )
            print("   ", item.description)

        back_option = len(entries) + 1
        print(f"{back_option}. Back")
        choice = input("Use item: ").strip()

        if choice == str(back_option):
            return

        try:
            selected_index = int(choice) - 1
        except ValueError:
            print("\nInvalid option.")
            continue

        if not 0 <= selected_index < len(entries):
            print("\nInvalid option.")
            continue

        item = entries[selected_index]

        try:
            result = use_item(
                player,
                item.key,
            )
        except InventoryError as error:
            print(f"\nCould not use item: {error}")
            continue

        print(
            f"\nUsed {item.name}. "
            f"{result.effect_key.title()} "
            f"+{result.amount_restored}"
        )


def _inventory_for(player):
    inventory = getattr(
        player,
        "inventory",
        None,
    )

    if inventory is None:
        inventory = {}
        player.inventory = inventory

    return inventory


def _require_item(item_key):
    item = get_item(item_key)

    if item is None:
        raise UnknownItemError(
            "Item does not exist."
        )

    return item


def _validate_quantity(quantity):
    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or quantity <= 0
    ):
        raise InvalidQuantityError(
            "Quantity must be a positive whole number."
        )


def _resource_values(player, effect_key):
    if effect_key == "health":
        return player.health, getattr(
            player,
            "max_health",
            100,
        )

    if effect_key == "energy":
        return player.energy, player.max_energy

    if effect_key == "happiness":
        return player.happiness, player.max_happiness

    raise ItemNotUsableError(
        "Item effect is not supported."
    )
