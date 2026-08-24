from dataclasses import dataclass
from datetime import datetime, timezone

from database.core.connection import get_connection
from game.player.regeneration import format_timestamp, parse_timestamp


@dataclass(frozen=True)
class EncounterRecord:
    wins: int
    attempts: int
    cooldown_seconds: int


def get_encounter_records(player_id, opponents, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT opponent_key, wins, attempts, last_fought_at
            FROM player_npc_combat
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchall()
    finally:
        connection.close()

    stored = {
        key: (wins, attempts, last_fought_at)
        for key, wins, attempts, last_fought_at in rows
    }
    records = {}
    for opponent in opponents:
        wins, attempts, last_fought_at = stored.get(
            opponent.key,
            (0, 0, None),
        )
        remaining = 0
        if last_fought_at is not None:
            elapsed = (now - parse_timestamp(last_fought_at)).total_seconds()
            remaining = max(
                0,
                int(opponent.cooldown_seconds - elapsed),
            )
        records[opponent.key] = EncounterRecord(
            wins=wins,
            attempts=attempts,
            cooldown_seconds=remaining,
        )
    return records


def record_encounter(player_id, opponent_key, victory, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO player_npc_combat (
                player_id,
                opponent_key,
                wins,
                attempts,
                last_fought_at
            )
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(player_id, opponent_key)
            DO UPDATE SET
                wins = wins + excluded.wins,
                attempts = attempts + 1,
                last_fought_at = excluded.last_fought_at
            """,
            (
                player_id,
                opponent_key,
                1 if victory else 0,
                format_timestamp(now),
            ),
        )
        connection.commit()
    finally:
        connection.close()
