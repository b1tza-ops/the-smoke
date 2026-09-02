"""The kit you bring to a job.

Five items have sat in the catalogue since the loot system shipped and
done nothing at all: a lockpick, bolt cutters, a glass cutter, duct tape
and a burner phone. They drop from crimes, they have a resale price, and
holding one has never once changed an outcome. The fastest thing a
player could do with any of them was sell it.

Now each one suits particular jobs. Carrying the right kit makes the
job more likely to come off, which gives loot a reason to stay in your
pockets rather than going straight to the fence -- and gives the fence
a rival for the first time.

Nothing here needs the tool. A job you cannot do without shopping first
is a job a new player is locked out of, and the whole crime ladder is
meant to be walkable from an empty inventory.
"""

from dataclasses import dataclass


# What one suitable tool is worth, in percentage points of success.
# Deliberately modest: mastery is worth up to 8 points and tools should
# not dwarf the thing a player earns by turning up.
TOOL_SUCCESS_BONUS = 4

# Two tools help; a third does not. Otherwise the answer to every job is
# "carry everything", which is not a decision.
MAXIMUM_TOOLS_PER_JOB = 2

# Botching a job with kit in your hands is how you leave it behind. This
# is what keeps tools in demand rather than a one-off purchase, and it
# is why they drop as loot in the first place.
TOOL_LOSS_CHANCE_ON_FAILURE = 25


@dataclass(frozen=True)
class Tool:
    key: str
    name: str
    # What it reads as when it helps, for the crime page.
    blurb: str


TOOLS = (
    Tool("lockpick", "Basic Lockpick", "the lock is the easy part"),
    Tool("bolt_cutters", "Bolt Cutters", "through the chain in seconds"),
    Tool("glass_cutter", "Glass Cutter", "a clean circle, no alarm"),
    Tool("duct_tape", "Duct Tape", "quiet, and quick to leave"),
    Tool("burner_phone", "Burner Phone", "nothing traceable on you"),
)
TOOLS_BY_KEY = {tool.key: tool for tool in TOOLS}


# Which kit suits which job. Chosen so that every tool is wanted
# somewhere and no single tool covers the whole ladder.
CRIME_TOOLS = {
    "camden_shoplift": (),
    "camden_market_stall": ("lockpick", "duct_tape"),
    "brixton_phone_snatch": ("burner_phone",),
    "brixton_warehouse": ("bolt_cutters", "lockpick"),
    "soho_pickpocket": ("burner_phone",),
    "soho_nightclub": ("lockpick", "duct_tape"),
    "shoreditch_gallery_lift": ("glass_cutter", "duct_tape"),
    "shoreditch_server_room": ("lockpick", "glass_cutter"),
    "hackney_lockup_raid": ("bolt_cutters", "glass_cutter"),
    "hackney_canal_handover": ("burner_phone", "duct_tape"),
}


def tools_for(crime_key):
    """The kit that suits this job, whether or not anyone owns it."""
    return tuple(
        TOOLS_BY_KEY[key]
        for key in CRIME_TOOLS.get(crime_key, ())
        if key in TOOLS_BY_KEY
    )


def usable_tools(inventory, crime_key):
    """The suitable kit this player is actually carrying.

    Capped, so a full toolbox is worth no more than a well-chosen pair.
    """
    carried = inventory or {}

    return tuple(
        tool for tool in tools_for(crime_key)
        if carried.get(tool.key, 0) > 0
    )[:MAXIMUM_TOOLS_PER_JOB]


def tool_bonus(inventory, crime_key):
    """Percentage points of success the kit is worth on this job."""
    return len(usable_tools(inventory, crime_key)) * TOOL_SUCCESS_BONUS


def tool_left_behind(inventory, crime_key, rng):
    """Which tool, if any, got dropped when the job went wrong.

    One at most. Losing the whole kit to a single bad roll would make
    carrying it feel worse than not bothering.
    """
    carried = usable_tools(inventory, crime_key)

    if not carried:
        return None

    if rng.randint(1, 100) > TOOL_LOSS_CHANCE_ON_FAILURE:
        return None

    return carried[rng.randint(0, len(carried) - 1)]
