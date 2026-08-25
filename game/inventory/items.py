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
    # What the item is worth, in pounds: the lowest price any shop sells
    # it for. The black market pays a fraction of this, which is what
    # keeps buying in one district and fencing in another a loss.
    value: int
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
        value=120,
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
        value=75,
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
        value=260,
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
        value=420,
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
        value=25,
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
        value=140,
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
        value=340,
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
        value=520,
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
        value=700,
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
        value=1450,
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
        value=240,
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
        value=300,
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
        value=780,
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
        value=900,
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
        value=1800,
        equipment_slot="body",
        defence_bonus=14,
    ),
    ItemDefinition("sports_drink", "Sports Drink", "boost", "Restores up to 30 energy.", "items/sports-drink.webp", True, 5, 140, "energy", 30),
    ItemDefinition("painkillers", "Painkillers", "medical", "Restores up to 15 health.", "items/painkillers.webp", True, 10, 80, "health", 15),
    ItemDefinition("bandage_roll", "Bandage Roll", "medical", "Restores up to 10 health.", "items/bandage-roll.webp", True, 15, 45, "health", 10),
    ItemDefinition("protein_bar", "Protein Bar", "boost", "Restores up to 8 energy.", "items/protein-bar.webp", True, 10, 35, "energy", 8),
    ItemDefinition("bolt_cutters", "Bolt Cutters", "utility", "Heavy cutters used in selected crimes.", "items/bolt-cutters.webp", True, 5, 460),
    ItemDefinition("glass_cutter", "Glass Cutter", "utility", "A precise tool for quiet entry.", "items/glass-cutter.webp", True, 10, 340),
    ItemDefinition("burner_phone", "Burner Phone", "utility", "A disposable phone for discreet work.", "items/burner-phone.webp", True, 5, 260),
    ItemDefinition("duct_tape", "Duct Tape", "utility", "Useful for improvised plans.", "items/duct-tape.webp", True, 10, 90),
    ItemDefinition("police_baton", "Police Baton", "weapon", "A balanced close-range weapon.", "items/police-baton.webp", False, 1, 620, equipment_slot="primary", strength_bonus=8),
    ItemDefinition("tire_iron", "Tyre Iron", "weapon", "Compact steel with a punishing swing.", "items/tyre-iron.webp", False, 1, 760, equipment_slot="primary", strength_bonus=10),
    ItemDefinition("hatchet", "Hatchet", "weapon", "A short, heavy chopping weapon.", "items/hatchet.webp", False, 1, 980, equipment_slot="primary", strength_bonus=12),
    ItemDefinition("survival_knife", "Survival Knife", "weapon", "A stronger secondary blade.", "items/survival-knife.webp", False, 1, 880, equipment_slot="secondary", strength_bonus=8),
    ItemDefinition("denim_jacket", "Reinforced Denim Jacket", "armour", "Street clothing with sewn-in padding.", "items/denim-jacket.webp", False, 1, 350, equipment_slot="body", defence_bonus=7),
    ItemDefinition("hard_hat", "Construction Hard Hat", "armour", "Basic protection against head impacts.", "items/hard-hat.webp", False, 1, 380, equipment_slot="head", defence_bonus=5),
    ItemDefinition("combat_gloves", "Combat Gloves", "armour", "Padded gloves with reinforced knuckles.", "items/combat-gloves.webp", False, 1, 520, equipment_slot="hands", defence_bonus=5),
    ItemDefinition("cargo_trousers", "Padded Cargo Trousers", "armour", "Hard-wearing trousers with light padding.", "items/cargo-trousers.webp", False, 1, 480, equipment_slot="legs", defence_bonus=5),
    ItemDefinition("trainers", "Street Trainers", "armour", "Light footwear that offers minimal protection.", "items/street-trainers.webp", False, 1, 220, equipment_slot="feet", defence_bonus=2),
    ItemDefinition("tactical_boots", "Tactical Boots", "armour", "Heavy boots designed for dangerous work.", "items/tactical-boots.webp", False, 1, 820, equipment_slot="feet", defence_bonus=7),
    ItemDefinition("reinforced_jeans", "Reinforced Jeans", "armour", "Denim lined with protective fibres.", "items/reinforced-jeans.webp", False, 1, 1100, equipment_slot="legs", defence_bonus=8),
    ItemDefinition("riot_helmet", "Riot Helmet", "armour", "A reinforced helmet with full face protection.", "items/riot-helmet.webp", False, 1, 1650, equipment_slot="head", defence_bonus=12),
    ItemDefinition(
        key="fish_and_chips",
        name="Fish and Chips",
        category="boost",
        description="A hot takeaway that restores up to 25 happiness.",
        image_filename="items/fish-and-chips.webp",
        stackable=True,
        max_quantity=10,
        value=55,
        effect_key="happiness",
        effect_amount=25,
    ),
    ItemDefinition(
        key="lockpick",
        name="Lockpick",
        category="utility",
        description="A simple tool for future crime actions.",
        image_filename="items/lockpick.webp",
        stackable=True,
        max_quantity=20,
        value=180,
    ),
)

ITEMS_BY_KEY = {
    item.key: item
    for item in ITEMS
}


def get_item(item_key):
    return ITEMS_BY_KEY.get(item_key)
