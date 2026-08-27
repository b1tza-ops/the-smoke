"""Fights that live longer than one request.

The pure turn arithmetic is in `game/combat/turns.py`; this is the part
that remembers a fight between clicks, spends the ammunition and the
throwables, and makes sure a turn cannot be taken twice.

Every write goes through BEGIN IMMEDIATE and re-reads the fight under
the write lock. A double-submitted turn is the obvious way to get two
attacks for one, and it is exactly what a refresh does.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import random

from database.core.connection import get_connection
from game.combat.pvp import PVP_ENERGY_COST, PvpError
from game.combat.turns import (
    FISTS,
    MAXIMUM_TURNS,
    THROWABLE_SLOT,
    TurnError,
    Weapon,
    choose,
    decide,
    fists,
    take_turn,
)
from game.inventory.equipment import WEAPON_SLOTS, get_equipment, loaded_rounds


@dataclass(frozen=True)
class Fight:
    id: int
    attacker_id: int
    defender_id: int
    defender_name: str
    approach: str
    turn: int
    attacker_health: int
    defender_health: int
    attacker_max_health: int
    defender_max_health: int
    reward_multiplier: float
    log: tuple
    status: str

    @property
    def open(self):
        return self.status == "open"

    @property
    def turns_left(self):
        return max(0, MAXIMUM_TURNS - self.turn)


def _now():
    return datetime.now(timezone.utc).isoformat()


def weapons_for(player_id):
    """Everything this player can swing, in the order they are shown.

    Fists come last and are always there. A firearm with no rounds of
    its calibre is listed but unusable, so the reason it cannot be fired
    is visible rather than the weapon simply vanishing.
    """
    equipped = get_equipment(player_id)
    rounds = loaded_rounds(player_id)
    carried = _carried(player_id)
    column = []

    for slot in WEAPON_SLOTS:
        item = equipped.get(slot)
        if item is None:
            continue

        ammo_key = getattr(item, "ammo_key", None)
        if ammo_key:
            available = rounds.get(ammo_key, 0)
        elif slot == THROWABLE_SLOT:
            available = carried.get(item.key, 0)
        else:
            available = None

        column.append(Weapon(
            slot=slot,
            key=item.key,
            name=item.name,
            damage=getattr(item, "strength_bonus", 0) or 0,
            ammo_key=ammo_key,
            available=available,
        ))

    column.append(fists())

    return tuple(column)


def _carried(player_id):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT item_key, quantity FROM player_inventory
            WHERE player_id = ? AND quantity > 0
            """,
            (player_id,),
        ).fetchall()
    finally:
        connection.close()

    return dict(rows)


def _use_one(connection, player_id, item_key):
    """Spend a single item, removing the row when it was the last one.

    `player_inventory.quantity` carries a CHECK that it stays above
    zero, so decrementing the last of something fails rather than
    emptying the stack. Throwing your final brick is exactly that case.
    """
    connection.execute(
        """
        DELETE FROM player_inventory
        WHERE player_id = ? AND item_key = ? AND quantity <= 1
        """,
        (player_id, item_key),
    )
    connection.execute(
        """
        UPDATE player_inventory SET quantity = quantity - 1
        WHERE player_id = ? AND item_key = ? AND quantity > 1
        """,
        (player_id, item_key),
    )


def _read(connection, fight_id, attacker_id):
    row = connection.execute(
        """
        SELECT f.id, f.attacker_id, f.defender_id, p.name, f.approach,
               f.turn, f.attacker_health, f.defender_health,
               f.attacker_max_health, f.defender_max_health,
               f.reward_multiplier, f.log_json, f.status
        FROM player_fights AS f
        JOIN players AS p ON p.id = f.defender_id
        WHERE f.id = ? AND f.attacker_id = ?
        """,
        (fight_id, attacker_id),
    ).fetchone()

    if row is None:
        return None

    return Fight(
        id=row[0], attacker_id=row[1], defender_id=row[2],
        defender_name=row[3], approach=row[4], turn=row[5],
        attacker_health=row[6], defender_health=row[7],
        attacker_max_health=row[8], defender_max_health=row[9],
        reward_multiplier=row[10], log=tuple(json.loads(row[11])),
        status=row[12],
    )


def get_open_fight(attacker_id):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT id FROM player_fights"
            " WHERE attacker_id = ? AND status = 'open'",
            (attacker_id,),
        ).fetchone()
        if row is None:
            return None
        return _read(connection, row[0], attacker_id)
    finally:
        connection.close()


def start_fight(
    attacker,
    defender_id,
    defender_health,
    defender_max_health,
    approach,
    reward_multiplier=1.0,
):
    """Open a fight and charge the energy for it.

    The energy is spent once, here, rather than per turn: the cost is
    for picking the fight, and charging by the turn would punish a
    player for a long one they did not choose.
    """
    now = _now()
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")

        already = connection.execute(
            "SELECT id FROM player_fights"
            " WHERE attacker_id = ? AND status = 'open'",
            (attacker.id,),
        ).fetchone()
        if already is not None:
            raise PvpError("You are already in a fight.")

        spent = connection.execute(
            "UPDATE players SET energy = energy - ?"
            " WHERE id = ? AND energy >= ?",
            (PVP_ENERGY_COST, attacker.id, PVP_ENERGY_COST),
        ).rowcount
        if spent != 1:
            raise PvpError(
                f"You need {PVP_ENERGY_COST} energy to start a fight."
            )

        cursor = connection.execute(
            """
            INSERT INTO player_fights (
                attacker_id, defender_id, approach, turn,
                attacker_health, defender_health,
                attacker_max_health, defender_max_health,
                reward_multiplier, log_json, status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, '[]', 'open', ?, ?)
            """,
            (
                attacker.id, defender_id, approach,
                attacker.health, defender_health,
                attacker.max_health, defender_max_health,
                reward_multiplier, now, now,
            ),
        )
        fight_id = cursor.lastrowid
        fight = _read(connection, fight_id, attacker.id)
        connection.commit()
        return fight
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def take_fight_turn(fight_id, attacker, defender, weapon_key, rng=None):
    """Swing once. Returns the outcome and the fight after it.

    Ammunition and throwables are spent in the same transaction that
    advances the turn, so a fight can never charge a player for a shot
    the turn counter did not record, or the other way round.
    """
    rng = rng or random.SystemRandom()
    now = _now()
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        fight = _read(connection, fight_id, attacker.id)

        if fight is None:
            raise PvpError("That fight is not yours.")
        if not fight.open:
            raise PvpError("That fight is already over.")

        weapon = choose(weapons_for(attacker.id), weapon_key)

        outcome = take_turn(
            fight.turn + 1,
            attacker,
            defender,
            weapon,
            fight.attacker_health,
            fight.defender_health,
            rng=rng,
        )

        if outcome.ammo_spent:
            _use_one(connection, attacker.id, outcome.ammo_spent)
        if outcome.throwable_spent:
            _use_one(connection, attacker.id, outcome.throwable_spent)
            # A thrown weapon is gone, so it cannot stay in the slot.
            connection.execute(
                """
                DELETE FROM player_equipment
                WHERE player_id = ? AND slot = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM player_inventory
                      WHERE player_id = ? AND item_key = ? AND quantity > 0
                  )
                """,
                (attacker.id, THROWABLE_SLOT,
                 attacker.id, outcome.throwable_spent),
            )

        log = list(fight.log) + [{
            "turn": outcome.turn,
            "weapon": outcome.weapon_key,
            "attacker_event": outcome.attacker_event,
            "attacker_damage": outcome.attacker_damage,
            "defender_event": outcome.defender_event,
            "defender_damage": outcome.defender_damage,
            "attacker": outcome.attacker_health,
            "defender": outcome.defender_health,
            "narration": list(outcome.narration),
        }]

        connection.execute(
            """
            UPDATE player_fights
            SET turn = ?, attacker_health = ?, defender_health = ?,
                log_json = ?, status = ?, updated_at = ?
            WHERE id = ? AND turn = ? AND status = 'open'
            """,
            (
                outcome.turn, outcome.attacker_health,
                outcome.defender_health, json.dumps(log),
                "finished" if outcome.finished else "open",
                now, fight_id, fight.turn,
            ),
        )

        updated = _read(connection, fight_id, attacker.id)
        connection.commit()
        return outcome, updated
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def flee(fight_id, attacker_id):
    """Walk away mid-fight. Costs the energy already spent, nothing more."""
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        changed = connection.execute(
            """
            UPDATE player_fights SET status = 'fled', updated_at = ?
            WHERE id = ? AND attacker_id = ? AND status = 'open'
            """,
            (_now(), fight_id, attacker_id),
        ).rowcount
        connection.commit()
        if changed != 1:
            raise PvpError("There is no fight to walk away from.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
