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
        image_filename="items/first-aid-kit.webp",
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
        image_filename="items/energy-drink.webp",
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
        equipment_slot="secondary",
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
        equipment_slot="body",
        defence_bonus=5,
    ),
    ItemDefinition(
        key="bottled_water",
        name="Bottled Water",
        category="boost",
        description="Restores up to 10 energy.",
        image_filename="items/bottled-water.webp",
        stackable=True,
        max_quantity=10,
        effect_key="energy",
        effect_amount=10,
    ),
    ItemDefinition(
        key="screwdriver",
        name="Heavy Screwdriver",
        category="weapon",
        description="A common tool that offers a small combat advantage.",
        image_filename="items/screwdriver.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="secondary",
        strength_bonus=3,
    ),
    ItemDefinition(
        key="claw_hammer",
        name="Claw Hammer",
        category="weapon",
        description="A solid improvised weapon.",
        image_filename="items/claw-hammer.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="primary",
        strength_bonus=7,
    ),
    ItemDefinition(
        key="crowbar",
        name="Crowbar",
        category="weapon",
        description="Heavy steel with serious leverage.",
        image_filename="items/crowbar.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="primary",
        strength_bonus=9,
    ),
    ItemDefinition(
        key="baseball_bat",
        name="Baseball Bat",
        category="weapon",
        description="A weighty bat with a taped grip.",
        image_filename="items/baseball-bat.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="primary",
        strength_bonus=11,
    ),
    ItemDefinition(
        key="machete",
        name="Machete",
        category="weapon",
        description="A formidable heavy blade.",
        image_filename="items/machete.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="primary",
        strength_bonus=15,
    ),
    ItemDefinition(
        key="leather_gloves",
        name="Leather Gloves",
        category="armour",
        description="Light hand protection.",
        image_filename="items/leather-gloves.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="hands",
        defence_bonus=2,
    ),
    ItemDefinition(
        key="work_boots",
        name="Reinforced Work Boots",
        category="armour",
        description="Steel-toe boots with modest protection.",
        image_filename="items/work-boots.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="feet",
        defence_bonus=3,
    ),
    ItemDefinition(
        key="motorcycle_helmet",
        name="Motorcycle Helmet",
        category="armour",
        description="Strong head protection with a dark visor.",
        image_filename="items/motorcycle-helmet.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="head",
        defence_bonus=7,
    ),
    ItemDefinition(
        key="heavy_coat",
        name="Heavy Coat",
        category="armour",
        description="A thick coat that softens incoming blows.",
        image_filename="items/heavy-coat.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="body",
        defence_bonus=9,
    ),
    ItemDefinition(
        key="stab_vest",
        name="Protective Vest",
        category="armour",
        description="Serious protection for dangerous streets.",
        image_filename="items/stab-vest.webp",
        stackable=False,
        max_quantity=1,
        equipment_slot="body",
        defence_bonus=14,
    ),
    ItemDefinition(
        key="lockpick",
        name="Lockpick",
        category="utility",
        description="A simple tool for future crime actions.",
        image_filename="items/lockpick.webp",
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
