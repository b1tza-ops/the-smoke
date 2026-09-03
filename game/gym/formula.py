"""Training maths, shared by the gym service and the web preview.

This is the one place a training gain is calculated. It deliberately
imports nothing from `game.gym.service`, so both `service` and the web
layer can rely on it without a cycle.

The shape follows Torn's: gain is linear in the stat being trained, so
training keeps paying as the stat grows, with a floor that keeps a new
player's first sessions worthwhile. Happiness scales the result and is
spent in proportion to the energy spent -- a heavier gym costs more
energy and proportionally more happiness, so the weight class decides
how big each commitment is, not how efficiently it burns happiness.

Because happiness falls and the stat rises as a batch runs, a batch
cannot be scored with a single multiplier. It is simulated one train at
a time, which also means N separate trains and one batch of N produce
exactly the same result.
"""

from dataclasses import dataclass

from game.player.happiness import training_multiplier_at


# Energy per train for each weight class. A lighter gym trains in
# smaller, more responsive chunks; a heavier one commits more energy --
# and proportionally more happiness -- to each one.
WEIGHT_CLASS_ENERGY = {
    "lightweight": 5,
    "middleweight": 10,
    "heavyweight": 25,
}

STANDARD_ENERGY_PER_TRAIN = 10

# Stat gained per point of energy by a beginner at a x1.0 gym on full
# happiness. A new player at Camden still gains exactly 1.0 a train.
GAIN_PER_ENERGY = 0.2

# Gain grows linearly with the stat being trained and doubles when it
# reaches this value: 2x at 2,000, 3x at 4,000, and so on. Without it,
# a flat gain that is transformative at 10 strength is invisible at
# 5,000, and training stops meaning anything.
STAT_SCALE = 2000

# Happiness spent per point of energy, rounded up to a whole point.
# Torn charges roughly half the energy spent; this is that, without the
# randomness, so the number the gym page previews is the number the
# player actually gets.
HAPPINESS_PER_ENERGY = 0.5


@dataclass(frozen=True)
class TrainingOutcome:
    trains: int
    energy_spent: int
    happiness_spent: int
    stat_gain: float


def trains_for(gym, energy):
    return energy // gym.energy_per_train


def happiness_cost(energy):
    """Happiness spent for a given amount of energy, rounded up."""
    return int(-(-energy * HAPPINESS_PER_ENERGY // 1))


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


def gain_per_train(gym, stat, stat_value=0, home_bonus_percent=0):
    """Gain for one train at full happiness.

    Multiplied before dividing so the arithmetic stays exact for any
    energy cost, not just the ones that happen to divide cleanly.

    `home_bonus_percent` is what is fitted at home -- the swimming pool
    and nothing else, at present. It multiplies the whole gain rather
    than the gym's own figure, so it is worth the same proportion at
    Camden Community as at The Lock.
    """
    return (
        gym.energy_per_train
        * gym.multiplier_for(stat)
        * GAIN_PER_ENERGY
        * (1 + stat_value / STAT_SCALE)
        * (1 + max(0, home_bonus_percent) / 100)
    )


def training_outcome(
    gym,
    stat,
    energy,
    stat_value=0,
    happiness=None,
    max_happiness=None,
    home_bonus_percent=0,
):
    """Resolve a training batch into gain, energy and happiness spent.

    `happiness` of None means the caller has no happiness to spend --
    gains are unscaled and nothing is deducted.
    """
    validate_training_energy(gym, energy)

    trains = trains_for(gym, energy)
    per_train_happiness = happiness_cost(gym.energy_per_train)
    remaining = happiness
    happiness_spent = 0
    total_gain = 0.0
    current_stat = stat_value

    for _ in range(trains):
        gain = gain_per_train(
            gym,
            stat,
            current_stat,
            home_bonus_percent,
        ) * training_multiplier_at(
            remaining,
            max_happiness,
        )
        total_gain += gain
        # The stat rises as the batch runs, so later trains in a long
        # session are worth slightly more than the first.
        current_stat += gain

        if remaining is not None:
            spent = min(remaining, per_train_happiness)
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
