from game.status import get_active_restriction
from game.travel import get_active_travel


VALID_BATTLE_STATS = (
    "strength",
    "defence",
    "speed",
    "dexterity",
)

TRAINING_ENERGY_COST = 10
TRAINING_STAT_GAIN = 2


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


def gym_menu(player):
    block_reason = get_training_block(player)

    if block_reason is not None:
        display_training_block(block_reason)
        return

    while True:
        print("\n===== GYM =====")
        print("Energy:", player.energy)

        print("\n1. Train Strength")
        print("2. Train Defence")
        print("3. Train Speed")
        print("4. Train Dexterity")
        print("5. Back")

        choice = input("Choose an option: ")

        if choice == "1":
            train(player, "strength")

        elif choice == "2":
            train(player, "defence")

        elif choice == "3":
            train(player, "speed")

        elif choice == "4":
            train(player, "dexterity")

        elif choice == "5":
            return

        else:
            print("Invalid option.")


def train(player, stat, now=None):
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

    if player.energy < TRAINING_ENERGY_COST:
        print("Not enough energy.")
        return False

    player.energy -= TRAINING_ENERGY_COST

    current_value = getattr(player, stat)

    setattr(
        player,
        stat,
        current_value + TRAINING_STAT_GAIN,
    )

    print("\nTraining complete!")
    print(
        stat.capitalize(),
        "+",
        TRAINING_STAT_GAIN,
    )
    print(
        "Energy -",
        TRAINING_ENERGY_COST,
    )

    return True