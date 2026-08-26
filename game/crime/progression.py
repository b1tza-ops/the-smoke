from dataclasses import dataclass


MAX_SUCCESS_CHANCE = 95
MAX_REPUTATION_BONUS_PERCENT = 15
REPUTATION_PER_BONUS_PERCENT = 25


@dataclass(frozen=True)
class MasteryTier:
    name: str
    minimum_xp: int
    success_bonus: int


@dataclass(frozen=True)
class CrimeProgression:
    crime_xp: int
    mastery_name: str
    mastery_bonus: int
    next_mastery_name: str | None
    next_mastery_xp: int | None
    district_reputation: int
    reputation_bonus_percent: int
    effective_success_chance: int
    min_reward: int
    max_reward: int


MASTERY_TIERS = (
    MasteryTier("Newcomer", 0, 0),
    MasteryTier("Practised", 100, 2),
    MasteryTier("Skilled", 300, 4),
    MasteryTier("Expert", 750, 6),
    MasteryTier("Master", 1500, 8),
)


def mastery_for_xp(crime_xp):
    crime_xp = max(0, int(crime_xp))
    current_index = 0

    for index, tier in enumerate(MASTERY_TIERS):
        if crime_xp < tier.minimum_xp:
            break
        current_index = index

    current = MASTERY_TIERS[current_index]
    next_tier = (
        MASTERY_TIERS[current_index + 1]
        if current_index + 1 < len(MASTERY_TIERS)
        else None
    )
    return current, next_tier


def reputation_bonus_percent(reputation):
    return min(
        MAX_REPUTATION_BONUS_PERCENT,
        max(0, int(reputation)) // REPUTATION_PER_BONUS_PERCENT,
    )


def apply_reputation_bonus(reward, bonus_percent):
    reward = max(0, int(reward))
    bonus = reward * max(0, int(bonus_percent)) // 100
    return reward + bonus, bonus


def crime_progression_for(player, crime, happiness_penalty=0):
    progress = getattr(player, "crime_progress", {}).get(crime.key, {})
    crime_xp = progress.get("xp", 0)
    mastery, next_mastery = mastery_for_xp(crime_xp)

    reputation = getattr(player, "district_reputation", {}).get(
        crime.district,
        0,
    )
    reward_bonus = reputation_bonus_percent(reputation)
    effective_chance = min(
        MAX_SUCCESS_CHANCE,
        max(
            1,
            crime.success_chance
            + mastery.success_bonus
            - max(0, happiness_penalty),
        ),
    )
    min_reward, _ = apply_reputation_bonus(crime.min_reward, reward_bonus)
    max_reward, _ = apply_reputation_bonus(crime.max_reward, reward_bonus)

    return CrimeProgression(
        crime_xp=crime_xp,
        mastery_name=mastery.name,
        mastery_bonus=mastery.success_bonus,
        next_mastery_name=(next_mastery.name if next_mastery else None),
        next_mastery_xp=(next_mastery.minimum_xp if next_mastery else None),
        district_reputation=reputation,
        reputation_bonus_percent=reward_bonus,
        effective_success_chance=effective_chance,
        min_reward=min_reward,
        max_reward=max_reward,
    )
