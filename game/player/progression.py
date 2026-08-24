BASE_MAX_HEALTH = 100
HEALTH_PER_LEVEL = 50


def max_health_for_level(level):
    if level < 1:
        raise ValueError("Level must be at least 1")
    return BASE_MAX_HEALTH + (level - 1) * HEALTH_PER_LEVEL


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
    previous_max_health = max_health_for_level(previous_level)

    player.xp += amount
    player.level = level_for_xp(player.xp)

    if hasattr(player, "max_health"):
        new_max_health = max_health_for_level(player.level)
        health_increase = new_max_health - previous_max_health
        player.max_health = new_max_health
        if hasattr(player, "health") and health_increase > 0:
            player.health = min(
                new_max_health,
                player.health + health_increase,
            )

    return player.level - previous_level