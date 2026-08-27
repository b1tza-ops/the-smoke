"""One exchange of a fight, resolved on its own.

`fight_player` settles a whole fight in a single call: twelve rounds of
dice, a winner, done. That is the right shape for a street opponent, and
the wrong shape for the attack screen, where a player picks a weapon,
sees what it did, and picks again.

Everything here is pure. It takes the state of a fight and a choice,
and returns the state of the fight afterwards. Persisting that is the
repository's job, which keeps this testable without a database and
keeps the arithmetic in one readable place.
"""

from dataclasses import dataclass
import random

from game.combat.stats import whole


# A fight cannot run for ever: somebody has to be able to walk away, and
# an unbounded exchange between two evenly matched players would never
# resolve. Torn stops at 25.
MAXIMUM_TURNS = 25

# What bare hands are worth. Deliberately not nothing -- a player who
# has spent everything still gets to fight.
FISTS = "fists"
FISTS_DAMAGE = 6

# A throwable is gone once it is thrown, which is what makes carrying a
# stack of them a decision rather than an obvious yes.
THROWABLE_SLOT = "throwable"


class TurnError(Exception):
    """Raised when a chosen weapon cannot be used this turn."""


@dataclass(frozen=True)
class Weapon:
    """A weapon as one turn sees it."""
    slot: str
    key: str
    name: str
    damage: int
    # None for anything that is not a firearm; otherwise the calibre it
    # spends a round of.
    ammo_key: str | None = None
    # How many of it the player is carrying. None means unlimited, which
    # is only ever true of fists.
    available: int | None = None

    @property
    def consumable(self):
        return self.slot == THROWABLE_SLOT

    @property
    def usable(self):
        return self.available is None or self.available > 0


@dataclass(frozen=True)
class TurnOutcome:
    """What one exchange did."""
    turn: int
    weapon_key: str
    attacker_event: str
    attacker_damage: int
    defender_event: str
    defender_damage: int
    attacker_health: int
    defender_health: int
    ammo_spent: str | None = None
    throwable_spent: str | None = None
    finished: bool = False
    victory: bool | None = None
    narration: tuple = ()


def fists():
    return Weapon(
        slot=FISTS,
        key=FISTS,
        name="Fists",
        damage=FISTS_DAMAGE,
    )


def choose(weapons, key):
    """The weapon a player asked for, or a refusal saying why.

    Refusing rather than silently falling back to fists: a player who
    meant to throw a petrol bomb and got a punch would rightly call
    that a bug.
    """
    for weapon in weapons:
        if weapon.key == key:
            if not weapon.usable:
                raise TurnError(f"You have no {weapon.name} left.")
            return weapon

    raise TurnError("You are not carrying that.")


def _swing(power, weapon_damage, defence, rng, spread):
    return max(1, whole(power) + weapon_damage
               + rng.randint(0, spread) - whole(defence) // 2)


def take_turn(
    turn,
    attacker,
    defender,
    weapon,
    attacker_health,
    defender_health,
    rng=None,
    accuracy_bonus=0,
):
    """Resolve one exchange: the player swings, then the defender does.

    The defender always answers unless they are down, which is what
    stops a turn-by-turn fight being strictly better than the old
    single-call one for the attacker.
    """
    rng = rng or random.SystemRandom()
    narration = []

    attacker_damage = 0
    defender_damage = 0
    attacker_event = "miss"
    defender_event = "miss"

    accuracy = max(25, min(95, 70 + accuracy_bonus
                           + (whole(attacker.dexterity)
                              - whole(defender.speed)) * 2))

    if rng.randint(1, 100) <= accuracy:
        attacker_event = "hit"
        attacker_damage = _swing(
            attacker.strength, weapon.damage, defender.defence, rng, 6
        )
        defender_health = max(0, defender_health - attacker_damage)
        narration.append(
            f"You strike with the {weapon.name.lower()} "
            f"for {attacker_damage}."
        )
    else:
        narration.append(f"Your {weapon.name.lower()} finds nothing.")

    if defender_health > 0:
        reply = max(25, min(92, 66 + (whole(defender.dexterity)
                                      - whole(attacker.speed)) * 2))
        if rng.randint(1, 100) <= reply:
            defender_event = "hit"
            defender_damage = _swing(
                defender.strength, FISTS_DAMAGE, attacker.defence, rng, 5
            )
            attacker_health = max(0, attacker_health - defender_damage)
            narration.append(f"They come back at you for {defender_damage}.")
        else:
            narration.append("They swing wide.")

    finished = (
        defender_health <= 0
        or attacker_health <= 0
        or turn >= MAXIMUM_TURNS
    )
    victory = None
    if finished:
        victory = decide(attacker_health, defender_health)
        narration.append(
            "They are not getting up." if victory
            else "You cannot keep this up."
        )

    return TurnOutcome(
        turn=turn,
        weapon_key=weapon.key,
        attacker_event=attacker_event,
        attacker_damage=attacker_damage,
        defender_event=defender_event,
        defender_damage=defender_damage,
        attacker_health=attacker_health,
        defender_health=defender_health,
        # Firing costs a round whether or not it connects.
        ammo_spent=weapon.ammo_key,
        throwable_spent=weapon.key if weapon.consumable else None,
        finished=finished,
        victory=victory,
        narration=tuple(narration),
    )


def decide(attacker_health, defender_health):
    """Who won, including when the turn limit ran out on both standing.

    A draw goes to the defender: starting a fight you cannot finish
    should not pay.
    """
    if defender_health <= 0:
        return True
    if attacker_health <= 0:
        return False

    return (defender_health / max(1, attacker_health)) < 1
