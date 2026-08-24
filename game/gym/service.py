from dataclasses import dataclass

from game.gym.definitions import (
    DEFAULT_GYM_KEY,
    GYMS,
    GymDefinition,
    get_district_gyms,
    get_gym,
)
from game.player.status import get_active_restriction
from game.world.travel import get_active_travel


VALID_BATTLE_STATS = (
    "strength",
    "defence",
    "speed",
    "dexterity",
)

TRAINING_ENERGY_COST = 10
TRAINING_STAT_GAIN = 2


class GymError(Exception):
    """Base exception for gym actions."""


class UnknownGymError(GymError):
    """Raised when a gym key is not recognised."""


class GymLockedError(GymError):
    """Raised when the player has not unlocked a gym."""


class GymLocationError(GymError):
    """Raised when the player is in the wrong district."""


class GymLevelError(GymError):
    """Raised when the player's level is too low."""


class GymMembershipFundsError(GymError):
    """Raised when membership costs more than carried cash."""


class GymAlreadyUnlockedError(GymError):
    """Raised when membership is purchased twice."""


class GymStatUnavailableError(GymError):
    """Raised when a gym does not train a selected stat."""


class TrainingRestrictedError(GymError):
    """Raised when player status prevents training."""


@dataclass(frozen=True)
class GymUnlockResult:
    gym_key: str
    membership_cost: int
    cash_balance: int


@dataclass(frozen=True)
class GymSelectionResult:
    gym_key: str


@dataclass(frozen=True)
class TrainingResult:
    gym_key: str
    stat: str
    energy_spent: int
    stat_gain: float
    new_stat_value: float


def get_training_block(player, now=None):
    active_travel = get_active_travel(
        player,
        now=now,
    )

    if active_travel is not None:
        return "travelling"

    restriction = get_active_restriction(
        player,
        now=now,
    )

    if restriction is not None:
        return restriction.kind

    return None


def display_training_block(block_reason):
    if block_reason == "jail":
        print(
            "\nYou cannot train while in jail."
        )

    elif block_reason == "hospital":
        print(
            "\nYou cannot train while in hospital."
        )

    elif block_reason == "travelling":
        print(
            "\nYou cannot train while travelling."
        )


def get_unlocked_gyms(player):
    unlocked = getattr(
        player,
        "unlocked_gyms",
        None,
    )

    if unlocked is None:
        return {DEFAULT_GYM_KEY}

    return unlocked


def unlock_gym(player, gym_key):
    gym = _require_gym(gym_key)
    unlocked = get_unlocked_gyms(player)

    if gym.key in unlocked:
        raise GymAlreadyUnlockedError(
            "You already have access to this gym."
        )

    _require_gym_location(player, gym)

    if player.level < gym.required_level:
        raise GymLevelError(
            f"Level {gym.required_level} is required."
        )

    if player.money < gym.membership_cost:
        raise GymMembershipFundsError(
            "Not enough carried cash for membership."
        )

    player.money -= gym.membership_cost
    unlocked.add(gym.key)
    player.unlocked_gyms = unlocked

    return GymUnlockResult(
        gym_key=gym.key,
        membership_cost=gym.membership_cost,
        cash_balance=player.money,
    )


def select_gym(player, gym_key):
    gym = _require_gym(gym_key)
    _require_gym_location(player, gym)

    if gym.key not in get_unlocked_gyms(player):
        raise GymLockedError(
            "Purchase membership before using this gym."
        )

    player.current_gym_key = gym.key

    return GymSelectionResult(
        gym_key=gym.key,
    )


def gym_menu(player):
    block_reason = get_training_block(player)

    if block_reason is not None:
        display_training_block(block_reason)
        return

    while True:
        district = getattr(
            player,
            "current_district",
            "camden",
        )
        gyms = get_district_gyms(district)

        print("\n===== GYMS =====")
        print("Location:", district.title())
        print("Energy:", player.energy)
        print("Cash: £", player.money, sep="")

        for number, gym in enumerate(gyms, start=1):
            access = (
                "Unlocked"
                if gym.key in get_unlocked_gyms(player)
                else f"£{gym.membership_cost:,} membership"
            )
            current = (
                " [Current]"
                if getattr(
                    player,
                    "current_gym_key",
                    DEFAULT_GYM_KEY,
                ) == gym.key
                else ""
            )
            print(
                f"{number}. {gym.name} "
                f"({access}){current}"
            )

        back_option = len(gyms) + 1
        print(f"{back_option}. Back")
        choice = input("Choose: ").strip()

        if choice == str(back_option):
            return

        try:
            selected_index = int(choice) - 1
        except ValueError:
            print("\nInvalid option.")
            continue

        if not 0 <= selected_index < len(gyms):
            print("\nInvalid option.")
            continue

        gym = gyms[selected_index]

        try:
            if gym.key not in get_unlocked_gyms(player):
                result = unlock_gym(
                    player,
                    gym.key,
                )
                print(
                    "\nMembership purchased for £",
                    f"{result.membership_cost:,}.",
                    sep="",
                )

            select_gym(
                player,
                gym.key,
            )
        except GymError as error:
            print(f"\nGym unavailable: {error}")
            continue

        _training_menu(
            player,
            gym,
        )


def train(
    player,
    stat,
    energy=TRAINING_ENERGY_COST,
    gym_key=None,
    now=None,
):
    if stat not in VALID_BATTLE_STATS:
        raise ValueError(
            f"Unknown battle stat: {stat}"
        )

    _validate_training_energy(energy)

    block_reason = get_training_block(
        player,
        now=now,
    )

    if block_reason is not None:
        raise TrainingRestrictedError(
            "You cannot train while "
            f"{'in ' if block_reason in {'hospital', 'jail'} else ''}"
            f"{block_reason}."
        )

    gym = _resolve_training_gym(
        player,
        gym_key,
    )
    _require_trainable_stat(gym, stat)

    if player.energy < energy:
        print("Not enough energy.")
        return False

    base_gain = (
        energy
        // TRAINING_ENERGY_COST
        * TRAINING_STAT_GAIN
    )
    stat_gain = round(
        base_gain * gym.multiplier_for(stat),
        2,
    )

    player.energy -= energy

    if hasattr(player, "last_energy_update"):
        from game.player.regeneration import format_timestamp
        from game.player.status import normalise_now

        player.last_energy_update = format_timestamp(
            normalise_now(now)
        )

    current_value = getattr(player, stat)
    new_value = round(
        current_value + stat_gain,
        2,
    )
    setattr(
        player,
        stat,
        new_value,
    )

    print("\nTraining complete!")
    print(stat.capitalize(), "+", stat_gain)
    print("Energy -", energy)

    return True


def calculate_training_gain(gym_key, stat, energy):
    if stat not in VALID_BATTLE_STATS:
        raise ValueError(
            f"Unknown battle stat: {stat}"
        )

    _validate_training_energy(energy)
    gym = _require_gym(gym_key)
    _require_trainable_stat(gym, stat)
    base_gain = (
        energy
        // TRAINING_ENERGY_COST
        * TRAINING_STAT_GAIN
    )

    return round(
        base_gain * gym.multiplier_for(stat),
        2,
    )


def _require_trainable_stat(gym, stat):
    if gym.multiplier_for(stat) <= 0:
        raise GymStatUnavailableError(
            f"{gym.name} does not train {stat.title()}."
        )


def _resolve_training_gym(player, gym_key):
    selected_key = (
        gym_key
        or getattr(
            player,
            "current_gym_key",
            DEFAULT_GYM_KEY,
        )
    )
    gym = _require_gym(selected_key)

    if gym.key not in get_unlocked_gyms(player):
        raise GymLockedError(
            "Purchase membership before using this gym."
        )

    _require_gym_location(player, gym)

    return gym


def _require_gym(gym_key):
    gym = get_gym(gym_key)

    if gym is None:
        raise UnknownGymError(
            "Gym does not exist."
        )

    return gym


def _require_gym_location(player, gym):
    district = getattr(
        player,
        "current_district",
        gym.district,
    )

    if district != gym.district:
        raise GymLocationError(
            f"Travel to {gym.district.title()} "
            "to use this gym."
        )


def _validate_training_energy(energy):
    if (
        isinstance(energy, bool)
        or not isinstance(energy, int)
        or energy <= 0
        or energy % TRAINING_ENERGY_COST != 0
    ):
        raise ValueError(
            "Training energy must be a positive "
            "multiple of 10."
        )


def _training_menu(player, gym):
    while True:
        print(f"\n===== {gym.name.upper()} =====")
        print("Energy:", player.energy)

        for number, stat in enumerate(
            VALID_BATTLE_STATS,
            start=1,
        ):
            multiplier = gym.multiplier_for(stat)
            print(
                f"{number}. Train {stat.title()} "
                f"(x{multiplier:g})"
            )

        back_option = len(VALID_BATTLE_STATS) + 1
        print(f"{back_option}. Back")
        choice = input("Choose: ").strip()

        if choice == str(back_option):
            return

        try:
            selected_index = int(choice) - 1
        except ValueError:
            print("\nInvalid option.")
            continue

        if not 0 <= selected_index < len(
            VALID_BATTLE_STATS
        ):
            print("\nInvalid option.")
            continue

        raw_energy = input(
            "Energy to use (multiples of 10): "
        ).strip()

        try:
            energy = int(raw_energy)
            train(
                player,
                VALID_BATTLE_STATS[selected_index],
                energy=energy,
                gym_key=gym.key,
            )
        except (ValueError, GymError) as error:
            print(f"\nTraining failed: {error}")
