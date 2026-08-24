from dataclasses import dataclass
import random

from game.player.progression import award_xp
from game.player.status import send_to_hospital


COMBAT_ENERGY_COST = 10
DEFEAT_HOSPITAL_SECONDS = 15 * 60


@dataclass(frozen=True)
class Opponent:
    key: str
    name: str
    description: str
    health: int
    strength: int
    defence: int
    speed: int
    dexterity: int
    cash_min: int
    cash_max: int
    xp_reward: int


@dataclass(frozen=True)
class CombatResult:
    victory: bool
    player_health: int
    opponent_health: int
    cash_reward: int
    xp_reward: int
    rounds: tuple[str, ...]
    hospital_until: str | None


CAMDEN_OPPONENT = Opponent(
    key="canal_yard_enforcer",
    name="Canal Yard Enforcer",
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
)


class CombatError(Exception):
    """Raised when a player cannot start an encounter."""


def get_combat_block(player):
    if player.current_district != "camden":
        return "This opponent operates in Camden."
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
    if player.energy < COMBAT_ENERGY_COST:
        return f"You need {COMBAT_ENERGY_COST} energy to fight."
    return None


def fight_camden_opponent(player, equipment, rng=None, now=None):
    block = get_combat_block(player)
    if block is not None:
        raise CombatError(block)

    rng = rng or random.SystemRandom()
    opponent = CAMDEN_OPPONENT
    player.energy -= COMBAT_ENERGY_COST
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
                    min(
                        92,
                        65 + (player.dexterity - opponent.speed) * 2,
                    ),
                )
                if rng.randint(1, 100) > accuracy:
                    log.append(
                        f"Round {round_number}: You miss."
                    )
                    continue
                damage = max(
                    1,
                    player_strength
                    + rng.randint(0, 6)
                    - opponent.defence // 2,
                )
                opponent_health = max(0, opponent_health - damage)
                log.append(
                    f"Round {round_number}: You deal {damage} damage."
                )
            else:
                accuracy = max(
                    25,
                    min(
                        90,
                        62 + (opponent.dexterity - player.speed) * 2,
                    ),
                )
                if rng.randint(1, 100) > accuracy:
                    log.append(
                        f"Round {round_number}: The enforcer misses."
                    )
                    continue
                damage = max(
                    1,
                    opponent.strength
                    + rng.randint(0, 5)
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
            log.append("The enforcer backs down.")
        else:
            player_health = 0
            log.append("You can no longer continue.")

    player.health = player_health
    if victory:
        cash_reward = rng.randint(
            opponent.cash_min,
            opponent.cash_max,
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
            DEFEAT_HOSPITAL_SECONDS,
            now=now,
        )

    return CombatResult(
        victory=victory,
        player_health=player.health,
        opponent_health=opponent_health,
        cash_reward=cash_reward,
        xp_reward=xp_reward,
        rounds=tuple(log),
        hospital_until=hospital_until,
    )
