from dataclasses import dataclass


ITEM_CATEGORIES = (
    "medical",
    "boost",
    "weapon",
    "armour",
    "utility",
)


@dataclass(frozen=True)
class ItemDefinition:
    key: str
    name: str
    category: str
    description: str
    stackable: bool
    max_quantity: int
    effect_key: str | None = None
    effect_amount: int = 0


ITEMS = (
    ItemDefinition(
        key="first_aid_kit",
        name="First Aid Kit",
        category="medical",
        description="Restores up to 25 health.",
        stackable=True,
        max_quantity=5,
        effect_key="health",
        effect_amount=25,
    ),
    ItemDefinition(
        key="energy_drink",
        name="Energy Drink",
        category="boost",
        description="Restores up to 20 energy.",
        stackable=True,
        max_quantity=5,
        effect_key="energy",
        effect_amount=20,
    ),
    ItemDefinition(
        key="kitchen_knife",
        name="Kitchen Knife",
        category="weapon",
        description="A basic close-range weapon.",
        stackable=False,
        max_quantity=1,
    ),
    ItemDefinition(
        key="padded_jacket",
        name="Padded Jacket",
        category="armour",
        description="Basic protection for a new player.",
        stackable=False,
        max_quantity=1,
    ),
    ItemDefinition(
        key="lockpick",
        name="Lockpick",
        category="utility",
        description="A simple tool for future crime actions.",
        stackable=True,
        max_quantity=20,
    ),
)

ITEMS_BY_KEY = {
    item.key: item
    for item in ITEMS
}


def get_item(item_key):
    return ITEMS_BY_KEY.get(item_key)
