from dataclasses import dataclass
import random

from game.combat.stats import whole
from game.player.progression import award_xp
from game.player.status import send_to_hospital


PVP_ENERGY_COST = 25
PVP_HOSPITAL_SECONDS = 15 * 60

# What a winner may do with someone who is already beaten. The fight
# itself decides none of this: it leaves the loser on the floor and the
# choice open, the way Torn's attack screen does.
#
# The three are exclusive on purpose. Taking their money and putting
# them out of action for a quarter of an hour are different prizes, and
# having to pick one is the whole decision.
AFTERMATH_LEAVE = "leave"
AFTERMATH_MUG = "mug"
AFTERMATH_HOSPITALISE = "hospitalise"
AFTERMATH_CHOICES = (
    AFTERMATH_LEAVE,
    AFTERMATH_MUG,
    AFTERMATH_HOSPITALISE,
)

# A won fight does not stay open for ever. Without this a player could
# beat someone, sit on the choice, and mug them the moment they came
# back rich. Past the window the fight settles as though they walked.
AFTERMATH_WINDOW_SECONDS = 5 * 60

MUG_MINIMUM_PERCENT = 5
MUG_MAXIMUM_PERCENT = 10
MUG_CASH_CAP = 500
APPROACHES = {
    "aggressive": {"damage": 1.20, "defence": 0.85, "accuracy": 0},
    "defensive": {"damage": 0.85, "defence": 1.25, "accuracy": 0},
    "precise": {"damage": 0.95, "defence": 1.0, "accuracy": 14},
    "evasive": {"damage": 0.90, "defence": 1.0, "accuracy": -8},
}


class PvpError(Exception):
    """Raised when a player-versus-player attack is not allowed."""


@dataclass(frozen=True)
class CombatRound:
    round_number: int
    actor: str
    event: str
    damage: int
    attacker_health: int
    defender_health: int


@dataclass(frozen=True)
class PvpResult:
    victory: bool
    attacker_health: int
    defender_health: int
    cash_stolen: int
    xp_reward: int
    rounds: tuple[CombatRound, ...]
    hospital_until: str | None
    # Rounds carry raw health values, so playback needs each fighter's
    # scale to draw a bar. Maximum health grows with level, so neither
    # of these can be assumed to be 100.
    attacker_start_health: int = 0
    attacker_max_health: int = 100
    defender_start_health: int = 0
    defender_max_health: int = 100


def get_pvp_block(attacker, defender=None):
    if attacker.hospital_until is not None:
        return "You cannot attack while in Hospital."
    if attacker.jail_until is not None:
        return "You cannot attack while in Jail."
    if attacker.travel_destination is not None:
        return "You cannot attack while travelling."
    if attacker.shift_until is not None:
        return "You cannot attack while working a shift."
    if attacker.health <= 0:
        return "You are not healthy enough to fight."
    if attacker.energy < PVP_ENERGY_COST:
        return f"You need {PVP_ENERGY_COST} energy to attack."
    if defender is None:
        return None
    if attacker.id == defender.id:
        return "You cannot attack yourself."
    if attacker.current_district != defender.current_district:
        return "That player is no longer in your district."
    if defender.hospital_until is not None:
        return "That player is already in Hospital."
    if defender.jail_until is not None:
        return "That player is in Jail."
    if defender.travel_destination is not None:
        return "That player is travelling."
    if defender.shift_until is not None:
        return "That player is protected while working."
    if defender.health <= 0:
        return "That player is not healthy enough to fight."
    return None


def estimate_target(attacker, target):
    attacker_power = _power(attacker)
    target_power = _power(target)
    ratio = target_power / max(1, attacker_power)
    if ratio < 0.60:
        return "Much weaker"
    if ratio < 0.85:
        return "Weaker"
    if ratio <= 1.18:
        return "Even match"
    if ratio <= 1.55:
        return "Stronger"
    return "Dangerous"


def fight_player(
    attacker,
    defender,
    attacker_equipment,
    defender_equipment,
    approach,
    reward_multiplier=1.0,
    rng=None,
    now=None,
):
    block = get_pvp_block(attacker, defender)
    if block is not None:
        raise PvpError(block)
    if approach not in APPROACHES:
        raise PvpError("Choose a valid combat approach.")

    rng = rng or random.SystemRandom()
    tactics = APPROACHES[approach]
    attacker.energy -= PVP_ENERGY_COST
    attacker_health = attacker.health
    defender_health = defender.health
    attacker_start_health = attacker_health
    defender_start_health = defender_health
    attacker_max_health = max(
        1, getattr(attacker, "max_health", 0) or attacker_health
    )
    defender_max_health = max(
        1, getattr(defender, "max_health", 0) or defender_health
    )
    rounds = []

    attacker_strength = whole(
        attacker.strength + attacker_equipment.strength_bonus
    )
    attacker_defence = whole(
        attacker.defence + attacker_equipment.defence_bonus
    )
    defender_strength = whole(
        defender.strength + defender_equipment.strength_bonus
    )
    defender_defence = whole(
        defender.defence + defender_equipment.defence_bonus
    )
    # Trained stats are fractional; randint needs whole numbers, and so
    # does a damage figure anybody has to read.
    attacker_speed = whole(attacker.speed)
    attacker_dexterity = whole(attacker.dexterity)
    defender_speed = whole(defender.speed)
    defender_dexterity = whole(defender.dexterity)

    for number in range(1, 16):
        attacker_first = (
            attacker_speed + rng.randint(0, max(1, attacker_dexterity))
            >= defender_speed + rng.randint(0, max(1, defender_dexterity))
        )
        order = ("attacker", "defender") if attacker_first else (
            "defender", "attacker"
        )
        for actor in order:
            if attacker_health <= 0 or defender_health <= 0:
                break
            if actor == "attacker":
                accuracy = _clamp(
                    62 + (attacker_dexterity - defender_speed) * 2
                    + tactics["accuracy"],
                    25,
                    94,
                )
                if approach == "evasive":
                    accuracy += 4
                if rng.randint(1, 100) > accuracy:
                    rounds.append(CombatRound(
                        number, actor, "miss", 0,
                        attacker_health, defender_health,
                    ))
                    continue
                damage = max(
                    1,
                    int(
                        (
                            attacker_strength + rng.randint(0, 7)
                            - defender_defence // 2
                        ) * tactics["damage"]
                    ),
                )
                defender_health = max(0, defender_health - damage)
            else:
                accuracy = _clamp(
                    62 + (defender_dexterity - attacker_speed) * 2
                    + (8 if approach == "aggressive" else 0)
                    + (-14 if approach == "evasive" else 0),
                    20,
                    92,
                )
                if rng.randint(1, 100) > accuracy:
                    rounds.append(CombatRound(
                        number, actor, "dodge" if approach == "evasive" else "miss",
                        0, attacker_health, defender_health,
                    ))
                    continue
                effective_defence = max(
                    1, int(attacker_defence * tactics["defence"])
                )
                damage = max(
                    1,
                    defender_strength + rng.randint(0, 7)
                    - effective_defence // 2,
                )
                attacker_health = max(0, attacker_health - damage)

            rounds.append(CombatRound(
                number, actor, "hit", damage,
                attacker_health, defender_health,
            ))

    victory = defender_health <= 0
    if attacker_health > 0 and defender_health > 0:
        victory = (
            attacker_health / max(1, attacker.health)
            > defender_health / max(1, defender.health)
        )
        if victory:
            defender_health = 0
        else:
            attacker_health = 0

    cash_stolen = 0
    xp_reward = 0
    hospital_until = None
    if victory:
        # Winning is worth the experience whatever the winner does
        # next; the money and the hospital bed are the part they choose.
        xp_reward = (
            0
            if reward_multiplier <= 0
            else max(
                5,
                int((20 + defender.level * 4) * reward_multiplier),
            )
        )
        award_xp(attacker, xp_reward)
        defender.health = 0
    else:
        # Losing is not a decision anybody gets to make.
        attacker.health = 0
        hospital_until = send_to_hospital(
            attacker, PVP_HOSPITAL_SECONDS, now=now
        )

    attacker.health = attacker_health
    if victory:
        defender.health = defender_health

    return PvpResult(
        victory=victory,
        attacker_health=attacker.health,
        defender_health=defender.health,
        cash_stolen=cash_stolen,
        xp_reward=xp_reward,
        rounds=tuple(rounds),
        hospital_until=hospital_until,
        attacker_start_health=attacker_start_health,
        attacker_max_health=attacker_max_health,
        defender_start_health=defender_start_health,
        defender_max_health=defender_max_health,
    )


@dataclass(frozen=True)
class Aftermath:
    """What the winner actually did with the person on the floor."""
    choice: str
    cash_stolen: int = 0
    hospital_until: str | None = None


def mug_takings(defender_money, percent, reward_multiplier=1.0):
    """What comes out of a beaten player's pockets.

    Capped twice over -- a share of what they carry, and a hard ceiling
    -- so a rich player is worth robbing without being ruinous to lose
    to. Banked money is never touched; that is what the bank is for.
    """
    if defender_money <= 0 or reward_multiplier <= 0:
        return 0

    return max(0, min(
        MUG_CASH_CAP,
        defender_money,
        int(defender_money * (percent / 100) * reward_multiplier),
    ))


def apply_aftermath(
    attacker,
    defender,
    choice,
    reward_multiplier=1.0,
    rng=None,
    now=None,
):
    """Carry out the winner's decision. Pure rules, no persistence.

    Called after `fight_player` has already settled who won, so it
    trusts that and only applies the consequence. Refusing an unknown
    choice rather than defaulting, because defaulting to `mug` would
    quietly take money nobody asked to take.
    """
    if choice not in AFTERMATH_CHOICES:
        raise PvpError("That is not something you can do.")

    rng = rng or random.SystemRandom()

    if choice == AFTERMATH_MUG:
        percent = rng.randint(MUG_MINIMUM_PERCENT, MUG_MAXIMUM_PERCENT)
        taken = mug_takings(
            defender.money, percent, reward_multiplier
        )
        defender.money -= taken
        attacker.money += taken
        return Aftermath(choice=choice, cash_stolen=taken)

    if choice == AFTERMATH_HOSPITALISE:
        defender.health = 0
        return Aftermath(
            choice=choice,
            hospital_until=send_to_hospital(
                defender, PVP_HOSPITAL_SECONDS, now=now
            ),
        )

    # Walking away costs the loser nothing but the fight itself.
    return Aftermath(choice=AFTERMATH_LEAVE)


def _power(player):
    return (
        player.strength + player.defence
        + player.speed + player.dexterity
    )


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))
