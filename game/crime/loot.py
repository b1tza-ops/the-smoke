"""What a crime leaves you carrying, on top of the cash.

Loot is the reason to commit a crime rather than punch an NPC for the
same money: it turns the item catalogue into something you acquire as
well as buy, and gives the black market a reason to exist.

Pools are district- and tier-appropriate. A Camden shoplift yields
whatever was by the till; the Hackney canal handover yields the sort of
kit somebody was moving for a reason.
"""

from game.inventory import ITEMS_BY_KEY


# crime key -> (percent chance of a drop on success, pool of item keys)
LOOT_TABLES = {
    "camden_shoplift": (
        45,
        (
            "bottled_water",
            "protein_bar",
            "bandage_roll",
            "fish_and_chips",
            "duct_tape",
        ),
    ),
    "camden_market_stall": (
        45,
        (
            "protein_bar",
            "fish_and_chips",
            "painkillers",
            "duct_tape",
            "first_aid_kit",
            "screwdriver",
        ),
    ),
    "brixton_phone_snatch": (
        45,
        (
            "energy_drink",
            "painkillers",
            "duct_tape",
            "burner_phone",
        ),
    ),
    "brixton_warehouse": (
        55,
        (
            "work_boots",
            "claw_hammer",
            "bolt_cutters",
            "crowbar",
            "tire_iron",
        ),
    ),
    "soho_pickpocket": (
        45,
        (
            "painkillers",
            "lockpick",
            "leather_gloves",
            "burner_phone",
        ),
    ),
    "soho_nightclub": (
        55,
        (
            "police_baton",
            "motorcycle_helmet",
            "survival_knife",
            "heavy_coat",
        ),
    ),
    "shoreditch_gallery_lift": (
        50,
        (
            "burner_phone",
            "glass_cutter",
            "denim_jacket",
            "combat_gloves",
        ),
    ),
    "shoreditch_server_room": (
        55,
        (
            "bolt_cutters",
            "cargo_trousers",
            "combat_gloves",
            "tactical_boots",
        ),
    ),
    "hackney_lockup_raid": (
        55,
        (
            "crowbar",
            "hatchet",
            "reinforced_jeans",
            "stab_vest",
        ),
    ),
    "hackney_canal_handover": (
        60,
        (
            "survival_knife",
            "machete",
            "riot_helmet",
            "stab_vest",
        ),
    ),
}


def loot_pool(crime_key):
    return LOOT_TABLES.get(crime_key)


def roll_loot(crime_key, rng):
    """One item key, or None when this attempt yields nothing.

    Takes the caller's `rng` so a seeded test gets a fixed outcome, the
    same way the cash reward and the failure roll already do.
    """
    table = LOOT_TABLES.get(crime_key)

    if table is None:
        return None

    chance, pool = table

    if rng.randint(1, 100) > chance:
        return None

    return pool[rng.randint(0, len(pool) - 1)]


def validate_tables():
    """Every pool must name real items, and every crime must have one.

    Called by the test suite rather than at import: the crime service
    imports this module, so importing it back at module level would
    close a cycle. The deferred import inside the function is safe.
    """
    from game.crime.service import CRIMES

    for crime in CRIMES:
        if crime.key not in LOOT_TABLES:
            raise ValueError(
                f"Crime '{crime.key}' has no loot table."
            )

    for crime_key, (chance, pool) in LOOT_TABLES.items():
        if not 0 < chance <= 100:
            raise ValueError(
                f"Loot chance for '{crime_key}' is not a percentage."
            )

        if not pool:
            raise ValueError(
                f"Loot pool for '{crime_key}' is empty."
            )

        for item_key in pool:
            if item_key not in ITEMS_BY_KEY:
                raise ValueError(
                    f"Loot pool for '{crime_key}' names unknown "
                    f"item '{item_key}'."
                )
