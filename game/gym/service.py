from dataclasses import dataclass

from game.gym.definitions import (
    DEFAULT_GYM_KEY,
    GYMS,
    GymDefinition,
    get_district_gyms,
    get_gym,
)
from game.gym.formula import (
    GAIN_PER_ENERGY,
    STANDARD_ENERGY_PER_TRAIN,
    training_outcome,
    validate_training_energy,
)
from game.player.status import get_active_restriction
from game.world.travel import get_active_travel


VALID_BATTLE_STATS = (
    "strength",
    "defence",
    "speed",
    "dexterity",
)

# Kept as public aliases -- both are exported from `game.gym`.
TRAINING_ENERGY_COST = STANDARD_ENERGY_PER_TRAIN
TRAINING_STAT_GAIN = GAIN_PER_ENERGY * STANDARD_ENERGY_PER_TRAIN


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


@dataclass(frozen=True)
class GymUnlockResult:
    gym_key: str
    membership_cost: int
    cash_balance: int


@dataclass(frozen=True)
class GymSelectionResult:
    gym_key: str


def get_training_block(player, now=None):
    if getattr(player, "shift_until", None) is not None:
        return "working a shift"

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

    elif block_reason == "working a shift":
        print(
            "\nYou cannot train while working a shift."
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
    energy=None,
    gym_key=None,
    now=None,
    home_bonus_percent=0,
):
    """Train one stat. `energy=None` means a single train at this gym.

    There is no fixed energy per train any more, so the default has to
    be resolved from the gym rather than a constant -- 10 energy is not
    even a legal amount at a heavyweight gym.
    """
    if stat not in VALID_BATTLE_STATS:
        raise ValueError(
            f"Unknown battle stat: {stat}"
        )

    block_reason = get_training_block(
        player,
        now=now,
    )

    if block_reason is not None:
        display_training_block(block_reason)
        return False

    # Gym before stat before energy: which gym a player is standing in
    # and whether it trains this stat at all are permanent facts, and
    # should be reported ahead of a fixable mistake about the amount.
    gym = _resolve_training_gym(
        player,
        gym_key,
    )
    _require_trainable_stat(gym, stat)

    if energy is None:
        energy = gym.energy_per_train

    validate_training_energy(gym, energy)

    if player.energy < energy:
        print("Not enough energy.")
        return False

    outcome = training_outcome(
        gym,
        stat,
        energy,
        stat_value=getattr(player, stat),
        happiness=getattr(player, "happiness", None),
        max_happiness=getattr(player, "max_happiness", None),
        home_bonus_percent=home_bonus_percent,
    )

    player.energy -= outcome.energy_spent

    if outcome.happiness_spent:
        player.happiness -= outcome.happiness_spent

    if hasattr(player, "last_energy_update"):
        from game.player.regeneration import format_timestamp
        from game.player.status import normalise_now

        player.last_energy_update = format_timestamp(
            normalise_now(now)
        )

    current_value = getattr(player, stat)
    new_value = round(
        current_value + outcome.stat_gain,
        2,
    )
    setattr(
        player,
        stat,
        new_value,
    )

    print("\nTraining complete!")
    print(
        f"{outcome.trains} × {gym.exercise_for(stat)}"
    )
    print(stat.capitalize(), "+", outcome.stat_gain)
    print("Energy -", outcome.energy_spent)

    if outcome.happiness_spent:
        print("Happiness -", outcome.happiness_spent)

    # Truthy on success and False when training was refused, so the
    # existing `if trained:` contract still holds -- but callers that
    # want the numbers no longer have to recompute them.
    return outcome


def calculate_training_gain(
    gym_key, stat, energy=None, player=None, home_bonus_percent=0
):
    """Preview the gain a training batch would produce.

    Shares `training_outcome` with `train()` so the figure shown on the
    page cannot drift from the one actually awarded.
    """
    if stat not in VALID_BATTLE_STATS:
        raise ValueError(
            f"Unknown battle stat: {stat}"
        )

    gym = _require_gym(gym_key)
    _require_trainable_stat(gym, stat)

    if energy is None:
        energy = gym.energy_per_train

    return training_outcome(
        gym,
        stat,
        energy,
        stat_value=getattr(player, stat, 0) or 0,
        happiness=getattr(player, "happiness", None),
        max_happiness=getattr(player, "max_happiness", None),
        home_bonus_percent=home_bonus_percent,
    ).stat_gain


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


def _training_menu(player, gym):
    while True:
        print(f"\n===== {gym.name.upper()} =====")
        print(
            f"{gym.weight_class.title()} · "
            f"{gym.energy_per_train} energy per train"
        )
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
            "Energy to use (multiples of "
            f"{gym.energy_per_train}): "
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
