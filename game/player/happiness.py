"""Happiness stat helpers shared by gym training and crime resolution.

Happiness sits at its maximum by default, so a player who stays out of
jail and hospital (or keeps topped up with items) trains and commits
crimes exactly as before. Time spent in jail or hospital knocks
happiness down, which softens training gains and crime odds until it
regenerates or is restored with an item.
"""

MIN_TRAINING_MULTIPLIER = 0.5
CRIME_HAPPINESS_PENALTY_CAP = 10


def happiness_ratio(player):
    happiness = getattr(player, "happiness", None)
    max_happiness = getattr(player, "max_happiness", None)

    if happiness is None or not max_happiness:
        return None

    return max(0.0, min(1.0, happiness / max_happiness))


def training_multiplier_at(happiness, max_happiness):
    """Training multiplier for a bare happiness value.

    Training spends happiness as it goes, so a batch of trains has to be
    scored against the happiness remaining at each one rather than the
    player's happiness when the batch started.
    """
    if happiness is None or not max_happiness:
        return 1.0

    ratio = max(0.0, min(1.0, happiness / max_happiness))

    return round(
        MIN_TRAINING_MULTIPLIER
        + (1 - MIN_TRAINING_MULTIPLIER) * ratio,
        4,
    )


def training_multiplier(player):
    return training_multiplier_at(
        getattr(player, "happiness", None),
        getattr(player, "max_happiness", None),
    )


def crime_success_penalty(player, cap=CRIME_HAPPINESS_PENALTY_CAP):
    ratio = happiness_ratio(player)

    if ratio is None:
        return 0

    return round(cap * (1 - ratio))
