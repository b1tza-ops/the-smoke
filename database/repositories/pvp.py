from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from database.core.connection import get_connection
from game.player.regeneration import format_timestamp, parse_timestamp


TARGET_PROTECTION_SECONDS = 10 * 60
REPEAT_REWARD_SECONDS = 60 * 60
DAILY_REWARDED_ATTACKS = 3


@dataclass(frozen=True)
class AttackLimits:
    protected_seconds: int
    repeat_seconds: int
    rewarded_attacks_today: int

    @property
    def blocked(self):
        return self.protected_seconds > 0

    @property
    def reward_multiplier(self):
        if self.rewarded_attacks_today >= DAILY_REWARDED_ATTACKS:
            return 0.0
        if self.repeat_seconds > 0:
            return 0.25
        return 1.0


def get_pvp_targets(attacker_id, district, now=None):
    now = _normalise_now(now)
    timestamp = format_timestamp(now)
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                id, user_id, name, level, health, money,
                strength, defence, speed, dexterity,
                jail_until, hospital_until, travel_destination,
                travel_until, shift_until
            FROM players
            WHERE id != ?
              AND (
                  CASE
                      WHEN travel_destination IS NOT NULL
                           AND travel_until <= ?
                      THEN travel_destination
                      ELSE current_district
                  END
              ) = ?
              AND NOT (
                  travel_destination IS NOT NULL
                  AND travel_until > ?
              )
            ORDER BY level ASC, name COLLATE NOCASE ASC
            LIMIT 40
            """,
            (attacker_id, timestamp, district, timestamp),
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "id": row[0],
            "user_id": row[1],
            "name": row[2],
            "level": row[3],
            "health": row[4],
            "money": row[5],
            "strength": row[6],
            "defence": row[7],
            "speed": row[8],
            "dexterity": row[9],
            "restricted": (
                _timestamp_active(row[10])
                or _timestamp_active(row[11])
                or (
                    row[12] is not None
                    and _timestamp_active(row[13])
                )
                or _timestamp_active(row[14])
            ),
        }
        for row in rows
    ]


def get_target_user_id(player_id):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT user_id FROM players WHERE id = ?",
            (player_id,),
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else row[0]


def get_attack_limits(attacker_id, defender_id, now=None):
    now = _normalise_now(now)
    connection = get_connection()
    try:
        last_against_target = connection.execute(
            """
            SELECT created_at
            FROM player_pvp_attacks
            WHERE attacker_id = ? AND defender_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (attacker_id, defender_id),
        ).fetchone()
        last_received = connection.execute(
            """
            SELECT created_at
            FROM player_pvp_attacks
            WHERE defender_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (defender_id,),
        ).fetchone()
        day_start = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        rewarded_today = connection.execute(
            """
            SELECT COUNT(*)
            FROM player_pvp_attacks
            WHERE attacker_id = ? AND defender_id = ?
              AND created_at >= ? AND reward_multiplier > 0
            """,
            (attacker_id, defender_id, day_start.isoformat()),
        ).fetchone()[0]
    finally:
        connection.close()

    return AttackLimits(
        protected_seconds=_remaining(
            last_received, TARGET_PROTECTION_SECONDS, now
        ),
        repeat_seconds=_remaining(
            last_against_target, REPEAT_REWARD_SECONDS, now
        ),
        rewarded_attacks_today=rewarded_today,
    )


def record_pvp_attack(
    attacker_id,
    defender_id,
    approach,
    result,
    reward_multiplier,
    now=None,
):
    now = _normalise_now(now)
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO player_pvp_attacks (
                attacker_id, defender_id, approach, outcome,
                cash_stolen, xp_reward, reward_multiplier,
                rounds_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attacker_id,
                defender_id,
                approach,
                "victory" if result.victory else "defeat",
                result.cash_stolen,
                result.xp_reward,
                reward_multiplier,
                json.dumps([
                    {
                        "round": event.round_number,
                        "actor": event.actor,
                        "event": event.event,
                        "damage": event.damage,
                    }
                    for event in result.rounds
                ]),
                now.isoformat(),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def get_recent_pvp_attacks(player_id, limit=12):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                combat.outcome, combat.cash_stolen, combat.xp_reward,
                combat.created_at, attacker.name, defender.name,
                combat.attacker_id = ?
            FROM player_pvp_attacks AS combat
            JOIN players AS attacker ON attacker.id = combat.attacker_id
            JOIN players AS defender ON defender.id = combat.defender_id
            WHERE combat.attacker_id = ? OR combat.defender_id = ?
            ORDER BY combat.id DESC LIMIT ?
            """,
            (player_id, player_id, player_id, limit),
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "outcome": row[0],
            "cash_stolen": row[1],
            "xp_reward": row[2],
            "created_at": row[3],
            "attacker_name": row[4],
            "defender_name": row[5],
            "was_attacker": bool(row[6]),
        }
        for row in rows
    ]


def _timestamp_active(value):
    if value is None:
        return False
    return parse_timestamp(value) > datetime.now(timezone.utc)


def _remaining(row, seconds, now):
    if row is None:
        return 0
    expiry = parse_timestamp(row[0]) + timedelta(seconds=seconds)
    return max(0, int((expiry - now).total_seconds()))


def _normalise_now(now):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)
