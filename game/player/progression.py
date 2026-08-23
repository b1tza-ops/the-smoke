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

    return player.level - previous_level