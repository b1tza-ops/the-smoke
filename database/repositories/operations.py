"""Storage for the debt campaign.

The rules themselves live in `game.operations`; this runs them inside a
transaction so two tabs cannot start the same operation twice.
"""

from types import SimpleNamespace

from database.core.connection import get_connection
from game.operations import (
    AVAILABLE,
    approach_shortfalls,
    campaign_status,
    get_operation,
)
from game.player.progression import level_for_xp, max_health_for_level
from game.world.districts import DISTRICTS


DISTRICT_NAMES = {
    district.key: district.name
    for district in DISTRICTS
}

# Enough of a player for the campaign rules, which only read level,
# district and the three approach stats plus energy and nerve.
_PLAYER_COLUMNS = (
    "level",
    "current_district",
    "energy",
    "nerve",
    "strength",
    "speed",
    "dexterity",
    "jail_until",
    "hospital_until",
    "travel_destination",
)

_REMAINING_SECONDS = """
    CASE
        WHEN ready_at IS NULL THEN 0
        ELSE MAX(
            0,
            CAST(
                (JULIANDAY(ready_at) - JULIANDAY(CURRENT_TIMESTAMP))
                * 86400 AS INTEGER
            )
        )
    END
"""


def _records(connection, user_id):
    rows = connection.execute(
        f"""
        SELECT
            operation_key,
            stage,
            approach,
            outcome_text,
            paydown,
            ready_at,
            {_REMAINING_SECONDS}
        FROM player_operations
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchall()

    return {
        row[0]: {
            "stage": row[1],
            "approach": row[2],
            "outcome_text": row[3],
            "paydown": row[4],
            "ready_at": row[5],
            "remaining_seconds": row[6],
        }
        for row in rows
    }


def _player(connection, user_id):
    row = connection.execute(
        f"""
        SELECT {", ".join(_PLAYER_COLUMNS)}
        FROM players
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    if row is None:
        raise ValueError("Your player record could not be found.")

    return SimpleNamespace(**dict(zip(_PLAYER_COLUMNS, row)))


def get_campaign(user_id):
    """Every operation's stage for this player, in campaign order."""
    connection = get_connection()

    try:
        return campaign_status(
            _player(connection, user_id),
            _records(connection, user_id),
            district_names=DISTRICT_NAMES,
        )
    finally:
        connection.close()


def start_operation(user_id, operation_key, approach_key):
    operation = get_operation(operation_key)

    if operation is None:
        raise ValueError("That operation does not exist.")

    approach = operation.approach_for(approach_key)

    if approach is None:
        raise ValueError("Choose one of the available approaches.")

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        background = connection.execute(
            "SELECT background FROM player_prologue WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if background is None or background[0] is None:
            raise ValueError("Complete your dossier first.")

        player = _player(connection, user_id)

        if player.jail_until is not None:
            raise ValueError("You cannot begin an operation from jail.")
        if player.hospital_until is not None:
            raise ValueError(
                "You cannot begin an operation from hospital."
            )
        if player.travel_destination is not None:
            raise ValueError(
                "You cannot begin an operation while travelling."
            )

        status = _status_for(
            campaign_status(
                player,
                _records(connection, user_id),
                district_names=DISTRICT_NAMES,
            ),
            operation_key,
        )

        if status.stage != AVAILABLE:
            raise ValueError(
                status.lock_reason
                or "That operation is not available."
            )

        shortfalls = approach_shortfalls(player, approach)

        if shortfalls:
            raise ValueError(
                f"You need {' and '.join(shortfalls)} "
                "for this approach."
            )

        connection.execute(
            """
            UPDATE players
            SET energy = energy - ?, nerve = nerve - ?
            WHERE user_id = ?
            """,
            (approach.energy, approach.nerve, user_id),
        )
        connection.execute(
            """
            INSERT INTO player_operations (
                user_id,
                operation_key,
                stage,
                approach,
                started_at,
                ready_at
            )
            VALUES (
                ?, ?, 'active', ?,
                CURRENT_TIMESTAMP,
                DATETIME(CURRENT_TIMESTAMP, ?)
            )
            """,
            (
                user_id,
                operation_key,
                approach_key,
                f"+{approach.duration_seconds} seconds",
            ),
        )
        connection.commit()

        return operation, approach
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def resolve_operation(user_id, operation_key):
    operation = get_operation(operation_key)

    if operation is None:
        raise ValueError("That operation does not exist.")

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        row = connection.execute(
            """
            SELECT stage, approach, ready_at
            FROM player_operations
            WHERE user_id = ? AND operation_key = ?
            """,
            (user_id, operation_key),
        ).fetchone()

        if row is None or row[0] != "active":
            raise ValueError("There is no active operation to resolve.")

        now = connection.execute(
            "SELECT CURRENT_TIMESTAMP"
        ).fetchone()[0]

        if row[2] is not None and row[2] > now:
            raise ValueError("The operation is still in progress.")

        approach = operation.approach_for(row[1])

        if approach is None:
            raise ValueError("The active operation could not be found.")

        debt = connection.execute(
            """
            SELECT debt_remaining
            FROM player_prologue
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        debt_remaining = debt[0] if debt else 0

        # The finale settles whatever is left, whichever way it is
        # played; every other operation pays down its own fixed amount.
        paydown = (
            debt_remaining
            if operation.clears_debt
            else min(approach.paydown, debt_remaining)
        )

        connection.execute(
            """
            UPDATE player_prologue
            SET debt_remaining = MAX(0, debt_remaining - ?)
            WHERE user_id = ?
            """,
            (paydown, user_id),
        )
        connection.execute(
            """
            UPDATE player_operations
            SET
                stage = 'completed',
                completed_at = CURRENT_TIMESTAMP,
                outcome_text = ?,
                paydown = ?
            WHERE user_id = ?
              AND operation_key = ?
              AND stage = 'active'
            """,
            (approach.outcome, paydown, user_id, operation_key),
        )

        current = connection.execute(
            "SELECT xp FROM players WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        new_xp = (current[0] if current else 0) + approach.xp
        new_level = level_for_xp(new_xp)
        new_max_health = max_health_for_level(new_level)

        # Levelling raises the health ceiling, and a player who was at
        # full health stays at full -- the same rule award_xp applies.
        connection.execute(
            """
            UPDATE players
            SET
                money = money + ?,
                xp = ?,
                level = ?,
                health = CASE
                    WHEN health >= max_health THEN ?
                    ELSE health
                END,
                max_health = ?,
                wanted_level = MIN(100, wanted_level + ?)
            WHERE user_id = ?
            """,
            (
                approach.cash,
                new_xp,
                new_level,
                new_max_health,
                new_max_health,
                approach.wanted,
                user_id,
            ),
        )
        connection.commit()

        return operation, approach, paydown
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _status_for(statuses, operation_key):
    for status in statuses:
        if status.operation.key == operation_key:
            return status

    raise ValueError("That operation does not exist.")
