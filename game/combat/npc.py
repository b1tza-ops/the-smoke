from dataclasses import dataclass
import random

from game.player.progression import award_xp
from game.player.status import send_to_hospital


COMBAT_ENERGY_COST = 10


@dataclass(frozen=True)
class Opponent:
    key: str
    district: str
    difficulty: str
    name: str
    initials: str
    description: str
    health: int
    strength: int
    defence: int
    speed: int
    dexterity: int
    cash_min: int
    cash_max: int
    xp_reward: int
    cooldown_seconds: int
    hospital_seconds: int
    energy_cost: int = COMBAT_ENERGY_COST


@dataclass(frozen=True)
class CombatResult:
    opponent_key: str
    victory: bool
    player_health: int
    opponent_health: int
    cash_reward: int
    xp_reward: int
    rounds: tuple[str, ...]
    hospital_until: str | None


OPPONENTS = (
    Opponent(
        key="market_runner",
        district="camden",
        difficulty="Starter",
        name="Market Runner",
        initials="MR",
        description=(
            "A reckless runner moving stolen phones through "
            "Camden Market. A suitable first target."
        ),
        health=42,
        strength=7,
        defence=6,
        speed=8,
        dexterity=7,
        cash_min=30,
        cash_max=55,
        xp_reward=15,
        cooldown_seconds=5 * 60,
        hospital_seconds=8 * 60,
        energy_cost=5,
    ),
    Opponent(
        key="canal_yard_enforcer",
        district="camden",
        difficulty="Standard",
        name="Canal Yard Enforcer",
        initials="CY",
        description=(
            "A local collector guarding a stolen-goods lockup "
            "beside Regent's Canal."
        ),
        health=70,
        strength=13,
        defence=11,
        speed=10,
        dexterity=10,
        cash_min=70,
        cash_max=125,
        xp_reward=35,
        cooldown_seconds=10 * 60,
        hospital_seconds=15 * 60,
        energy_cost=10,
    ),
    Opponent(
        key="soho_door_enforcer",
        district="soho",
        difficulty="Hard",
        name="Soho Door Enforcer",
        initials="SD",
        description=(
            "A veteran doorman protecting an illegal cash room. "
            "Proper weapons and a complete armour set are advised."
        ),
        health=135,
        strength=25,
        defence=22,
        speed=18,
        dexterity=17,
        cash_min=120,
        cash_max=200,
        xp_reward=80,
        cooldown_seconds=20 * 60,
        hospital_seconds=30 * 60,
        energy_cost=15,
    ),
)
OPPONENTS_BY_KEY = {opponent.key: opponent for opponent in OPPONENTS}
CAMDEN_OPPONENT = OPPONENTS_BY_KEY["canal_yard_enforcer"]


class CombatError(Exception):
    """Raised when a player cannot start an encounter."""


def get_district_opponents(district):
    return tuple(
        opponent
        for opponent in OPPONENTS
        if opponent.district == district
    )


# What is left of a payout once you have outgrown the fight. Rolling
# someone far beneath you is not lucrative, and without this the hardest
# opponent you can beat is the only rational thing to do forever: the
# win rate goes from 2% to 100% between stats 10 and 20, so there is no
# gradient to price the reward against -- only how far past them you are.
OUTGROWN_PAYOUT_FLOOR = 0.15


def combat_power(strength, defence, speed, dexterity):
    return strength + defence + speed + dexterity


def payout_share(player, opponent):
    """How much of an opponent's purse is still worth taking.

    Full price while they are your equal or better; falling away as you
    outgrow them, never quite to nothing.

    Measured on trained stats alone, deliberately. Counting the loadout
    too would mean equipping your best gun cut your own income, which
    would have players fighting barehanded to earn more -- gear is what
    you brought, not who you are.
    """
    theirs = combat_power(
        opponent.strength,
        opponent.defence,
        opponent.speed,
        opponent.dexterity,
    )
    mine = combat_power(
        player.strength,
        player.defence,
        player.speed,
        player.dexterity,
    )

    return max(
        OUTGROWN_PAYOUT_FLOOR,
        min(1.0, theirs / max(1, mine)),
    )


def get_combat_block(player, opponent=None):
    if opponent is not None and player.current_district != opponent.district:
        return f"{opponent.name} operates in {opponent.district.title()}."
    if player.hospital_until is not None:
        return "You cannot fight while in Hospital."
    if player.jail_until is not None:
        return "You cannot fight while in Jail."
    if player.travel_destination is not None:
        return "You cannot fight while travelling."
    if player.shift_until is not None:
        return "You cannot fight while working a shift."
    if player.health <= 0:
        return "You are not healthy enough to fight."

    if opponent is not None:
        if player.energy < opponent.energy_cost:
            return (
                f"You need {opponent.energy_cost} energy to fight "
                f"{opponent.name}."
            )
        return None

    # Asked about the player rather than a particular fight, which is
    # what the fight page does when it renders itself. Every guard above
    # already handled a missing opponent; this one read
    # `opponent.energy_cost` regardless and took the whole page down
    # with an AttributeError -- for healthy players only, since anyone
    # in hospital, in jail, travelling or on a shift returned before
    # reaching it. The page worked for exactly the people who could not
    # use it.
    cheapest = cheapest_fight_cost(player.current_district)

    if cheapest is not None and player.energy < cheapest:
        return f"You need {cheapest} energy to fight anyone here."

    return None


def cheapest_fight_cost(district):
    """The least energy any fight in this district costs, or None.

    None means there is nobody to fight there, which is not a reason to
    stop a player doing anything -- it just means this district has no
    opponents in it.
    """
    costs = [
        opponent.energy_cost
        for opponent in get_district_opponents(district)
    ]

    return min(costs) if costs else None


def fight_opponent(player, equipment, opponent, rng=None, now=None):
    block = get_combat_block(player, opponent)
    if block is not None:
        raise CombatError(block)

    rng = rng or random.SystemRandom()
    player.energy -= opponent.energy_cost
    player_health = player.health
    opponent_health = opponent.health
    log = []
    player_strength = player.strength + equipment.strength_bonus
    player_defence = player.defence + equipment.defence_bonus

    for round_number in range(1, 13):
        player_first = (
            player.speed + rng.randint(0, max(1, player.dexterity))
            >= opponent.speed + rng.randint(0, opponent.dexterity)
        )
        turns = ("player", "opponent") if player_first else (
            "opponent", "player"
        )
        for attacker in turns:
            if player_health <= 0 or opponent_health <= 0:
                break
            if attacker == "player":
                accuracy = max(
                    25,
                    min(92, 65 + (player.dexterity - opponent.speed) * 2),
                )
                if rng.randint(1, 100) > accuracy:
                    log.append(f"Round {round_number}: You miss.")
                    continue
                damage = max(
                    1,
                    player_strength + rng.randint(0, 6)
                    - opponent.defence // 2,
                )
                opponent_health = max(0, opponent_health - damage)
                log.append(
                    f"Round {round_number}: You deal {damage} damage."
                )
            else:
                accuracy = max(
                    25,
                    min(90, 62 + (opponent.dexterity - player.speed) * 2),
                )
                if rng.randint(1, 100) > accuracy:
                    log.append(
                        f"Round {round_number}: {opponent.name} misses."
                    )
                    continue
                damage = max(
                    1,
                    opponent.strength + rng.randint(0, 5)
                    - player_defence // 2,
                )
                player_health = max(0, player_health - damage)
                log.append(
                    f"Round {round_number}: You take {damage} damage."
                )

    victory = opponent_health <= 0
    if opponent_health > 0 and player_health > 0:
        victory = player_health / max(1, player.health) > (
            opponent_health / opponent.health
        )
        if victory:
            opponent_health = 0
            log.append(f"{opponent.name} backs down.")
        else:
            player_health = 0
            log.append("You can no longer continue.")

    player.health = player_health
    if victory:
        cash_reward = round(
            rng.randint(opponent.cash_min, opponent.cash_max)
            * payout_share(player, opponent)
        )
        player.money += cash_reward
        award_xp(player, opponent.xp_reward)
        hospital_until = None
        xp_reward = opponent.xp_reward
    else:
        cash_reward = 0
        xp_reward = 0
        hospital_until = send_to_hospital(
            player,
            opponent.hospital_seconds,
            now=now,
        )

    return CombatResult(
        opponent_key=opponent.key,
        victory=victory,
        player_health=player.health,
        opponent_health=opponent_health,
        cash_reward=cash_reward,
        xp_reward=xp_reward,
        rounds=tuple(log),
        hospital_until=hospital_until,
    )


def fight_camden_opponent(player, equipment, rng=None, now=None):
    return fight_opponent(
        player,
        equipment,
        CAMDEN_OPPONENT,
        rng=rng,
        now=now,
    )
