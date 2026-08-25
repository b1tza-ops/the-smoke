import random
from dataclasses import dataclass

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
    xp_reward: int = 0
    crime_xp_reward: int = 0
    reputation_reward: int = 0
    damage: int = 0
    levels_gained: int = 0
    wanted_gained: int = 0
    consequence: str | None = None
    jail_until: str | None = None
    hospital_until: str | None = None

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
        min_reward=60,
        max_reward=140,
        xp_reward=25,
        crime_xp_reward=18,
        reputation_reward=4,
        wanted_gain=2,
        jail_chance=15,
        jail_seconds=60 * 60,
        hospital_chance=8,
        hospital_seconds=120,
    ),
    CrimeDefinition(
        key="brixton_phone_snatch",
        name="Snatch a phone in Brixton",
        district="Brixton",
        nerve_cost=3,
        success_chance=72,
        min_reward=40,
        max_reward=100,
        xp_reward=15,
        crime_xp_reward=12,
        reputation_reward=3,
        wanted_gain=2,
        jail_chance=12,
        jail_seconds=30 * 60,
        hospital_chance=8,
        hospital_seconds=120,
    ),
    CrimeDefinition(
        key="brixton_warehouse",
        name="Break into a Brixton warehouse",
        district="Brixton",
        nerve_cost=7,
        success_chance=42,
        min_reward=180,
        max_reward=480,
        xp_reward=55,
        crime_xp_reward=30,
        reputation_reward=7,
        wanted_gain=5,
        jail_chance=25,
        jail_seconds=12 * 60 * 60,
        hospital_chance=20,
        hospital_seconds=300,
    ),

    CrimeDefinition(
        key="soho_pickpocket",
        name="Pickpocket in Soho",
        district="Soho",
        nerve_cost=4,
        success_chance=65,
        min_reward=50,
        max_reward=150,
        xp_reward=25,
        crime_xp_reward=18,
        reputation_reward=4,

        wanted_gain=2,
        jail_chance=15,
        jail_seconds=30 * 60,
        hospital_chance=8,
        hospital_seconds=120,
    ),
    CrimeDefinition(
        key="soho_nightclub",
        name="Raid a Soho nightclub office",
        district="Soho",
        nerve_cost=8,
        success_chance=38,
        min_reward=250,
        max_reward=650,
        xp_reward=65,
        crime_xp_reward=35,
        reputation_reward=8,
        wanted_gain=6,
        jail_chance=30,
        jail_seconds=3 * 24 * 60 * 60,
        hospital_chance=25,
        hospital_seconds=420,
    ),
    CrimeDefinition(
        key="shoreditch_gallery_lift",
        name="Lift a piece from a Shoreditch gallery",
        district="Shoreditch",
        nerve_cost=6,
        success_chance=55,
        min_reward=180,
        max_reward=420,
        xp_reward=45,
        crime_xp_reward=28,
        reputation_reward=6,
        wanted_gain=4,
        jail_chance=22,
        jail_seconds=90 * 60,
        hospital_chance=15,
        hospital_seconds=240,
    ),
    CrimeDefinition(
        key="shoreditch_server_room",
        name="Empty a Shoreditch start-up's server room",
        district="Shoreditch",
        nerve_cost=10,
        success_chance=34,
        min_reward=400,
        max_reward=900,
        xp_reward=85,
        crime_xp_reward=45,
        reputation_reward=10,
        wanted_gain=8,
        jail_chance=35,
        jail_seconds=4 * 24 * 60 * 60,
        hospital_chance=28,
        hospital_seconds=600,
    ),
    CrimeDefinition(
        key="hackney_lockup_raid",
        name="Raid a Hackney canal lock-up",
        district="Hackney",
        nerve_cost=9,
        success_chance=45,
        min_reward=350,
        max_reward=750,
        xp_reward=75,
        crime_xp_reward=40,
        reputation_reward=9,
        wanted_gain=6,
        jail_chance=28,
        jail_seconds=2 * 24 * 60 * 60,
        hospital_chance=22,
        hospital_seconds=480,
    ),
    CrimeDefinition(
        key="hackney_canal_handover",
        name="Intercept a handover on the Hackney canal",
        district="Hackney",
        nerve_cost=12,
        success_chance=28,
        min_reward=700,
        max_reward=1500,
        xp_reward=120,
        crime_xp_reward=60,
        reputation_reward=14,
        wanted_gain=12,
        jail_chance=40,
        jail_seconds=5 * 24 * 60 * 60,
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

    success_roll = rng.randint(1, 100)
    effective_chance = max(
        1,
        crime.success_chance - crime_success_penalty(player),
    )

    if success_roll <= effective_chance:
        reward = rng.randint(
            crime.min_reward,
            crime.max_reward,
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

        return CrimeResult(
            attempted=True,
            crime_key=crime.key,
            crime_name=crime.name,
            district=crime.district,
            success=True,
            nerve_spent=crime.nerve_cost,
            cash_reward=reward,
            xp_reward=crime.xp_reward,
            crime_xp_reward=crime.crime_xp_reward,
            reputation_reward=crime.reputation_reward,
            levels_gained=levels_gained,
            wanted_gained=crime.wanted_gain,
        )

    return _resolve_failed_crime(
        player=player,
        crime=crime,
        rng=rng,
        now=now,
    )


def _resolve_failed_crime(
    player,
    crime,
    rng,
    now=None,
):
    consequence_roll = rng.randint(1, 100)

    hospital_cutoff = crime.hospital_chance
    jail_cutoff = (
        crime.hospital_chance
        + crime.jail_chance
    )

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