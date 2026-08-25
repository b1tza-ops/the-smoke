"""Training maths, shared by the gym service and the web preview.

This is the one place a training gain is calculated. It deliberately
imports nothing from `game.gym.service`, so both `service` and the web
layer can rely on it without a cycle.

A train spends energy *and* happiness. Because happiness also scales the
gain, a batch of trains cannot be scored with a single multiplier -- the
happiness left at each train differs. So a batch is simulated one train
at a time, which also means N separate trains and one batch of N produce
exactly the same result.
"""

from dataclasses import dataclass

from game.player.happiness import training_multiplier_at


# Energy per train for each weight class. A lighter gym trains in
# smaller, more responsive chunks; a heavier one commits more energy per
# train and so spends happiness far more slowly.
WEIGHT_CLASS_ENERGY = {
    "lightweight": 5,
    "middleweight": 10,
    "heavyweight": 25,
}

STANDARD_ENERGY_PER_TRAIN = 10
STAT_GAIN_PER_STANDARD_TRAIN = 2
HAPPINESS_PER_TRAIN = 5


@dataclass(frozen=True)
class TrainingOutcome:
    trains: int
    energy_spent: int
    happiness_spent: int
    stat_gain: float


def trains_for(gym, energy):
    return energy // gym.energy_per_train


def validate_training_energy(gym, energy):
    cost = gym.energy_per_train

    if (
        isinstance(energy, bool)
        or not isinstance(energy, int)
        or energy <= 0
        or energy % cost != 0
    ):
        raise ValueError(
            "Training energy must be a positive "
            f"multiple of {cost}."
        )


def gain_per_train(gym, stat):
    """Gain for one train at full happiness.

    Multiplied before dividing so the arithmetic stays exact for any
    energy cost, not just the ones that happen to divide cleanly.
    """
    return (
        gym.energy_per_train
        * STAT_GAIN_PER_STANDARD_TRAIN
        * gym.multiplier_for(stat)
        / STANDARD_ENERGY_PER_TRAIN
    )


def training_outcome(
    gym,
    stat,
    energy,
    happiness=None,
    max_happiness=None,
):
    """Resolve a training batch into gain, energy and happiness spent.

    `happiness` of None means the caller has no happiness to spend --
    gains are unscaled and nothing is deducted.
    """
    validate_training_energy(gym, energy)

    trains = trains_for(gym, energy)
    per_train = gain_per_train(gym, stat)
    remaining = happiness
    happiness_spent = 0
    total_gain = 0.0

    for _ in range(trains):
        total_gain += per_train * training_multiplier_at(
            remaining,
            max_happiness,
        )

        if remaining is not None:
            spent = min(remaining, HAPPINESS_PER_TRAIN)
            remaining -= spent
            happiness_spent += spent

    return TrainingOutcome(
        trains=trains,
        # Charge for the trains actually performed rather than the
        # energy passed in, so the two can never drift apart.
        energy_spent=trains * gym.energy_per_train,
        happiness_spent=happiness_spent,
        stat_gain=round(total_gain, 2),
    )
