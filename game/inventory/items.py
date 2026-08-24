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
    image_filename: str
    stackable: bool
    max_quantity: int
    effect_key: str | None = None
    effect_amount: int = 0
    equipment_slot: str | None = None
    strength_bonus: int = 0
    defence_bonus: int = 0


ITEMS = (
    ItemDefinition(
        key="first_aid_kit",
        name="First Aid Kit",
        category="medical",
        description="Restores up to 25 health.",
        image_filename="shop-first-aid.svg",
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
        image_filename="shop-energy-drink.svg",
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
        image_filename="items/kitchen-knife.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="weapon",
        strength_bonus=5,
    ),
    ItemDefinition(
        key="padded_jacket",
        name="Padded Jacket",
        category="armour",
        description="Basic protection for a new player.",
        image_filename="items/padded-hoodie.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="armour",
        defence_bonus=5,
    ),
    ItemDefinition(
        key="lockpick",
        name="Lockpick",
        category="utility",
        description="A simple tool for future crime actions.",
        image_filename="shop-lockpick.svg",
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
