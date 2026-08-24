BASE_MAX_HEALTH = 100
MAX_HEALTH_PER_LEVEL = 10


def max_health_for_level(level):
    if level < 1:
        raise ValueError("Level must be at least 1")

    return BASE_MAX_HEALTH + (level - 1) * MAX_HEALTH_PER_LEVEL


def xp_required_for_level(level):
    if level < 1:
        raise ValueError("Level must be at least 1")

    return 50 * (level - 1) * level


def level_for_xp(xp):
    if xp < 0:
        raise ValueError("XP cannot be negative")

    level = 1

    while xp >= xp_required_for_level(level + 1):
        level += 1

    return level


def award_xp(player, amount):
    if amount < 0:
        raise ValueError("XP award cannot be negative")

    previous_level = player.level

    player.xp += amount
    player.level = level_for_xp(player.xp)

    levels_gained = player.level - previous_level

    if levels_gained > 0 and hasattr(player, "max_health"):
        previous_max_health = player.max_health
        new_max_health = max_health_for_level(player.level)

        if (
            hasattr(player, "health")
            and player.health >= previous_max_health
        ):
            player.health = new_max_health

        player.max_health = new_max_health

    return levels_gained