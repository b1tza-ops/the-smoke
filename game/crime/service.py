import random
from dataclasses import dataclass

from game.crime.loot import roll_loot
from game.crime.progression import (
    jail_chance_with_heat,
    apply_reputation_bonus,
    crime_progression_for,
)
from game.economy.fence import fence_price
from game.crime.tools import tool_left_behind
from game.inventory import (
    ITEMS_BY_KEY,
    InventoryError,
    InventoryFullError,
    ItemLimitError,
    add_item,
    remove_item,
)
from game.player.happiness import crime_success_penalty
from game.player.progression import award_xp
from game.world.travel import get_active_travel

from game.player.status import (
    add_wanted,
    get_active_restriction,
    send_to_hospital,
    send_to_jail,
)


@dataclass(frozen=True)
class CrimeDefinition:
    key: str
    name: str
    district: str
    nerve_cost: int
    success_chance: int
    min_reward: int
    max_reward: int
    xp_reward: int
    crime_xp_reward: int
    reputation_reward: int
    wanted_gain: int
    jail_chance: int
    jail_seconds: int
    hospital_chance: int
    hospital_seconds: int
    min_damage: int = 5
    max_damage: int = 15


@dataclass(frozen=True)
class CrimeResult:
    attempted: bool
    crime_key: str
    crime_name: str
    district: str
    success: bool
    reason: str | None = None
    nerve_spent: int = 0
    cash_reward: int = 0
    base_cash_reward: int = 0
    cash_bonus: int = 0
    effective_success_chance: int = 0
    mastery_bonus: int = 0
    reputation_bonus_percent: int = 0
    xp_reward: int = 0
    crime_xp_reward: int = 0
    reputation_reward: int = 0
    damage: int = 0
    levels_gained: int = 0
    wanted_gained: int = 0
    consequence: str | None = None
    jail_until: str | None = None
    hospital_until: str | None = None
    loot_item_key: str | None = None
    loot_item_name: str | None = None
    # Paid instead of the item when there is nowhere to put it.
    loot_cash: int = 0

CRIMES = (
    CrimeDefinition(
        key="camden_shoplift",
        name="Shoplift on Camden High Street",
        district="Camden",
        nerve_cost=2,
        success_chance=80,
        min_reward=20,
        max_reward=60,
        xp_reward=10,
        crime_xp_reward=10,
        reputation_reward=2,
        wanted_gain=1,
        jail_chance=10,
        jail_seconds=10 * 60,
        hospital_chance=5,
        hospital_seconds=60,

    ),
    CrimeDefinition(
        key="camden_market_stall",
        name="Rob a Camden market stall",
        district="Camden",
        nerve_cost=4,
        success_chance=65,
        min_reward=95,
        max_reward=225,
        xp_reward=25,
        crime_xp_reward=18,
        reputation_reward=4,
        wanted_gain=2,
        jail_chance=15,
        jail_seconds=20 * 60,
        hospital_chance=8,
        hospital_seconds=120,
    ),
    CrimeDefinition(
        key="brixton_phone_snatch",
        name="Snatch a phone in Brixton",
        district="Brixton",
        nerve_cost=3,
        success_chance=72,
        min_reward=50,
        max_reward=125,
        xp_reward=15,
        crime_xp_reward=12,
        reputation_reward=3,
        wanted_gain=2,
        jail_chance=12,
        jail_seconds=15 * 60,
        hospital_chance=8,
        hospital_seconds=120,
    ),
    CrimeDefinition(
        key="brixton_warehouse",
        name="Break into a Brixton warehouse",
        district="Brixton",
        nerve_cost=7,
        success_chance=42,
        min_reward=340,
        max_reward=905,
        xp_reward=55,
        crime_xp_reward=30,
        reputation_reward=7,
        wanted_gain=5,
        jail_chance=25,
        jail_seconds=35 * 60,
        hospital_chance=20,
        hospital_seconds=300,
    ),

    CrimeDefinition(
        key="soho_pickpocket",
        name="Pickpocket in Soho",
        district="Soho",
        nerve_cost=4,
        success_chance=65,
        min_reward=80,
        max_reward=240,
        xp_reward=25,
        crime_xp_reward=18,
        reputation_reward=4,

        wanted_gain=2,
        jail_chance=15,
        jail_seconds=20 * 60,
        hospital_chance=8,
        hospital_seconds=120,
    ),
    CrimeDefinition(
        key="soho_nightclub",
        name="Raid a Soho nightclub office",
        district="Soho",
        nerve_cost=8,
        success_chance=38,
        min_reward=480,
        max_reward=1250,
        xp_reward=65,
        crime_xp_reward=35,
        reputation_reward=8,
        wanted_gain=6,
        jail_chance=30,
        jail_seconds=40 * 60,
        hospital_chance=25,
        hospital_seconds=420,
    ),
    CrimeDefinition(
        key="shoreditch_gallery_lift",
        name="Lift a piece from a Shoreditch gallery",
        district="Shoreditch",
        nerve_cost=6,
        success_chance=55,
        min_reward=220,
        max_reward=515,
        xp_reward=45,
        crime_xp_reward=28,
        reputation_reward=6,
        wanted_gain=4,
        jail_chance=22,
        jail_seconds=30 * 60,
        hospital_chance=15,
        hospital_seconds=240,
    ),
    CrimeDefinition(
        key="shoreditch_server_room",
        name="Empty a Shoreditch start-up's server room",
        district="Shoreditch",
        nerve_cost=10,
        success_chance=34,
        min_reward=865,
        max_reward=1945,
        xp_reward=85,
        crime_xp_reward=45,
        reputation_reward=10,
        wanted_gain=8,
        jail_chance=35,
        jail_seconds=50 * 60,
        hospital_chance=28,
        hospital_seconds=600,
    ),
    CrimeDefinition(
        key="hackney_lockup_raid",
        name="Raid a Hackney canal lock-up",
        district="Hackney",
        nerve_cost=9,
        success_chance=45,
        min_reward=565,
        max_reward=1210,
        xp_reward=75,
        crime_xp_reward=40,
        reputation_reward=9,
        wanted_gain=6,
        jail_chance=28,
        jail_seconds=45 * 60,
        hospital_chance=22,
        hospital_seconds=480,
    ),
    CrimeDefinition(
        key="hackney_canal_handover",
        name="Intercept a handover on the Hackney canal",
        district="Hackney",
        nerve_cost=12,
        success_chance=28,
        min_reward=1475,
        max_reward=3160,
        xp_reward=120,
        crime_xp_reward=60,
        reputation_reward=14,
        wanted_gain=12,
        jail_chance=40,
        jail_seconds=60 * 60,
        hospital_chance=32,
        hospital_seconds=900,
    ),
)

CRIMES_BY_KEY = {crime.key: crime for crime in CRIMES}


def get_crime(crime_key):
    return CRIMES_BY_KEY[crime_key]

def commit_crime(player, crime, rng=None, now=None):
    if rng is None:
        rng = random

    active_travel = get_active_travel(
        player,
        now=now,
    )

    if active_travel is not None:
        return CrimeResult(
            attempted=False,
            crime_key=crime.key,
            crime_name=crime.name,
            district=crime.district,
            success=False,
            reason="travelling",
        )

    crime_district_key = crime.district.casefold()

    if player.current_district != crime_district_key:
        return CrimeResult(
            attempted=False,
            crime_key=crime.key,
            crime_name=crime.name,
            district=crime.district,
            success=False,
            reason="wrong_district",
        )

    if player.nerve < crime.nerve_cost:
        return CrimeResult(
            attempted=False,
            crime_key=crime.key,
            crime_name=crime.name,
            district=crime.district,
            success=False,
            reason="not_enough_nerve",
        )

    player.nerve -= crime.nerve_cost

    progress = _crime_progress_for(
        player,
        crime.key,
    )
    progress["attempts"] += 1

    add_wanted(
        player,
        amount=crime.wanted_gain,
        now=now,
    )

    progression = crime_progression_for(
        player,
        crime,
        happiness_penalty=crime_success_penalty(player),
    )
    success_roll = rng.randint(1, 100)

    if success_roll <= progression.effective_success_chance:
        base_reward = rng.randint(
            crime.min_reward,
            crime.max_reward,
        )
        reward, cash_bonus = apply_reputation_bonus(
            base_reward,
            progression.reputation_bonus_percent,
        )

        player.money += reward
        levels_gained = award_xp(
            player,
            crime.xp_reward,
        )

        progress["xp"] += crime.crime_xp_reward
        progress["successes"] += 1

        reputation = _district_reputation_for(player)

        reputation[crime.district] = (
            reputation.get(crime.district, 0)
            + crime.reputation_reward
        )

        loot_item, loot_cash = _collect_loot(
            player,
            crime,
            rng,
        )
        player.money += loot_cash

        return CrimeResult(
            attempted=True,
            crime_key=crime.key,
            crime_name=crime.name,
            district=crime.district,
            success=True,
            nerve_spent=crime.nerve_cost,
            cash_reward=reward,
            base_cash_reward=base_reward,
            cash_bonus=cash_bonus,
            effective_success_chance=progression.effective_success_chance,
            mastery_bonus=progression.mastery_bonus,
            reputation_bonus_percent=progression.reputation_bonus_percent,
            xp_reward=crime.xp_reward,
            crime_xp_reward=crime.crime_xp_reward,
            reputation_reward=crime.reputation_reward,
            levels_gained=levels_gained,
            wanted_gained=crime.wanted_gain,
            loot_item_key=loot_item.key if loot_item else None,
            loot_item_name=loot_item.name if loot_item else None,
            loot_cash=loot_cash,
        )

    return _resolve_failed_crime(
        player=player,
        crime=crime,
        rng=rng,
        now=now,
    )


def _collect_loot(player, crime, rng):
    """Roll for loot and try to carry it home.

    Returns the item and the cash paid instead of it. A player whose
    bag is full, or who already owns the one machete they are allowed,
    offloads it on the way rather than losing the drop -- so the item is
    the good outcome and the cash is the consolation, never nothing.
    """
    item_key = roll_loot(crime.key, rng)

    if item_key is None:
        return None, 0

    item = ITEMS_BY_KEY[item_key]

    try:
        add_item(player, item_key)
    except (InventoryFullError, ItemLimitError):
        return item, fence_price(item, crime.district.casefold())

    return item, 0


def _resolve_failed_crime(
    player,
    crime,
    rng,
    now=None,
):
    # Botching a job with kit in your hands is how you leave it behind,
    # which is what keeps tools in demand instead of a one-off buy.
    dropped = tool_left_behind(
        getattr(player, "inventory", None), crime.key, rng
    )
    if dropped is not None:
        try:
            remove_item(player, dropped.key, 1)
        except InventoryError:
            dropped = None

    consequence_roll = rng.randint(1, 100)

    # Heat sharpens the odds of being taken in. The wanted level was
    # accrued by every crime already and read by nothing; this is what
    # it is for.
    jail_chance = jail_chance_with_heat(
        crime.jail_chance,
        getattr(player, "wanted_level", 0),
    )

    hospital_cutoff = crime.hospital_chance
    jail_cutoff = crime.hospital_chance + jail_chance

    if consequence_roll <= hospital_cutoff:
        damage = rng.randint(
            crime.min_damage,
            crime.max_damage,
        )

        player.health = max(
            0,
            player.health - damage,
        )

        hospital_until = send_to_hospital(
            player,
            duration_seconds=crime.hospital_seconds,
            now=now,
        )

        return CrimeResult(
            attempted=True,
            crime_key=crime.key,
            crime_name=crime.name,
            district=crime.district,
            success=False,
            nerve_spent=crime.nerve_cost,
            damage=damage,
            wanted_gained=crime.wanted_gain,
            consequence="hospital",
            hospital_until=hospital_until,
        )

    if consequence_roll <= jail_cutoff:
        jail_until = send_to_jail(
            player,
            duration_seconds=crime.jail_seconds,
            now=now,
        )

        return CrimeResult(
            attempted=True,
            crime_key=crime.key,
            crime_name=crime.name,
            district=crime.district,
            success=False,
            nerve_spent=crime.nerve_cost,
            wanted_gained=crime.wanted_gain,
            consequence="jail",
            jail_until=jail_until,
        )

    damage = rng.randint(
        crime.min_damage,
        crime.max_damage,
    )

    player.health = max(
        0,
        player.health - damage,
    )

    return CrimeResult(
        attempted=True,
        crime_key=crime.key,
        crime_name=crime.name,
        district=crime.district,
        success=False,
        nerve_spent=crime.nerve_cost,
        damage=damage,
        wanted_gained=crime.wanted_gain,
        consequence="damage",
    )

def crimes_menu(player):
    while True:
        active_travel = get_active_travel(player)

        if active_travel is not None:
            remaining_minutes = (
                active_travel.remaining_seconds + 59
            ) // 60

            print(
                "\nYou cannot commit crimes "
                "while travelling."
            )
            print(
                f"Arrival in approximately "
                f"{remaining_minutes} minute(s)."
            )
            return

        restriction = get_active_restriction(player)

        if restriction is not None:
            remaining_minutes = (
                restriction.remaining_seconds + 59
            ) // 60

            if restriction.kind == "jail":
                print(
                    "\nYou cannot commit crimes "
                    "while in jail."
                )
                print(
                    f"Release in approximately "
                    f"{remaining_minutes} minute(s)."
                )
            else:
                print(
                    "\nYou cannot commit crimes "
                    "while in hospital."
                )
                print(
                    f"Discharge in approximately "
                    f"{remaining_minutes} minute(s)."
                )

            return

        available_crimes = tuple(
            crime
            for crime in CRIMES
            if crime.district.casefold()
            == player.current_district
        )

        print("\n===== CRIMES =====")
        print(
            "District:",
            player.current_district.title(),
        )
        print("Nerve:", player.nerve)

        if not available_crimes:
            print(
                "\nThere are no available crimes "
                "in this district."
            )
            return

        for number, crime in enumerate(
            available_crimes,
            start=1,
        ):
            print(
                f"{number}. {crime.name} "
                f"({crime.nerve_cost} nerve)"
            )

        back_option = len(available_crimes) + 1
        print(f"{back_option}. Back")

        choice = input("Choose: ").strip()

        if choice == str(back_option):
            return

        try:
            selected_index = int(choice) - 1
        except ValueError:
            print("Invalid option.")
            continue

        if not 0 <= selected_index < len(
            available_crimes
        ):
            print("Invalid option.")
            continue

        crime = available_crimes[
            selected_index
        ]

        result = commit_crime(player, crime)
        display_crime_result(player, result)

def display_crime_result(player, result):
    if result.reason == "travelling":
        print(
            "\nYou cannot commit crimes "
            "while travelling."
        )
        return

    if result.reason == "wrong_district":
        print(
            "\nYou must travel to "
            f"{result.district} for this crime."
        )
        return

    if result.reason == "not_enough_nerve":
        print("\nNot enough nerve.")
        return

    print("\nAttempting:", result.crime_name)
    print(
        f"Wanted +{result.wanted_gained} "
        f"(current level: {player.wanted_level})"
    )

    if result.success:
        print("Crime successful!")
        print("You made £", result.cash_reward)
        print("XP +", result.xp_reward)
        print(
            "Crime XP +",
            result.crime_xp_reward,
        )
        print(
            f"{result.district} reputation +",
            result.reputation_reward,
        )

        if result.levels_gained > 0:
            print(
                f"Level up! You are now level "
                f"{player.level}."
            )

        return

    print("Crime failed!")

    if result.consequence == "jail":
        print(
            "You were arrested and sent to jail."
        )
        print(
            "Release time:",
            result.jail_until,
        )

    elif result.consequence == "hospital":
        print(
            "You lost",
            result.damage,
            "health.",
        )
        print("You were taken to hospital.")
        print(
            "Discharge time:",
            result.hospital_until,
        )

    else:
        print(
            "You lost",
            result.damage,
            "health.",
        )

def _crime_progress_for(player, crime_key):
    if not hasattr(player, "crime_progress"):
        player.crime_progress = {}

    return player.crime_progress.setdefault(
        crime_key,
        {
            "xp": 0,
            "attempts": 0,
            "successes": 0,
        },
    )


def _district_reputation_for(player):
    if not hasattr(
        player,
        "district_reputation",
    ):
        player.district_reputation = {}

    return player.district_reputation
