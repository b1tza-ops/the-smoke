from dataclasses import dataclass
from datetime import datetime, timezone

from database.core.connection import get_connection
from game.combat.contracts import (
    CONTRACTS_BY_KEY,
    daily_contracts,
    daily_key,
    reset_seconds,
)
from game.player.progression import level_for_xp


class ContractClaimError(Exception):
    """Raised when a daily PvP contract cannot be claimed."""


@dataclass(frozen=True)
class ContractState:
    contract: object
    progress: int
    claimed: bool

    @property
    def complete(self):
        return self.progress >= self.contract.target

    @property
    def percent(self):
        return min(
            100,
            int(self.progress / self.contract.target * 100),
        )


@dataclass(frozen=True)
class ContractBoard:
    day_key: str
    reset_seconds: int
    contracts: tuple[ContractState, ...]


@dataclass(frozen=True)
class ContractClaim:
    contract_name: str
    cash_reward: int
    xp_reward: int
    item_key: str | None


def get_contract_board(player_id, now=None):
    now = _now(now)
    day = daily_key(now)
    active = daily_contracts(now)
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT contract_key, progress, claimed_at
            FROM player_pvp_contracts
            WHERE player_id = ? AND day_key = ?
            """,
            (player_id, day),
        ).fetchall()
    finally:
        connection.close()
    stored = {
        key: (progress, claimed_at)
        for key, progress, claimed_at in rows
    }
    return ContractBoard(
        day_key=day,
        reset_seconds=reset_seconds(now),
        contracts=tuple(
            ContractState(
                contract=contract,
                progress=stored.get(contract.key, (0, None))[0],
                claimed=stored.get(contract.key, (0, None))[1] is not None,
            )
            for contract in active
        ),
    )


def record_contract_fight(
    player_id,
    result,
    approach=None,
    rated=True,
    now=None,
):
    """Credit a finished fight against today's contracts.

    Takes either kind of fight. A street fight passes no approach, which
    means the approach contracts simply do not move -- picking
    Aggressive or Evasive is a choice that only exists against a person.

    `rated` is the player-fight guard: an unrated attack (the same
    target over and over) earns no contract progress either. Street
    fights are always counted, since the per-opponent cooldown already
    limits them.
    """
    if not rated:
        return
    now = _now(now)
    day = daily_key(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        for contract in daily_contracts(now):
            amount = _progress_amount(contract, result, approach)
            if amount <= 0:
                continue
            connection.execute(
                """
                INSERT INTO player_pvp_contracts (
                    player_id, day_key, contract_key,
                    progress, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(player_id, day_key, contract_key)
                DO UPDATE SET
                    progress = progress + excluded.progress,
                    updated_at = excluded.updated_at
                WHERE claimed_at IS NULL
                """,
                (
                    player_id, day, contract.key,
                    amount, now.isoformat(),
                ),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def claim_contract(player_id, contract_key, now=None):
    now = _now(now)
    day = daily_key(now)
    active = {
        contract.key: contract
        for contract in daily_contracts(now)
    }
    contract = active.get(contract_key)
    if contract is None:
        raise ContractClaimError(
            "That contract is not active today."
        )

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT progress, claimed_at
            FROM player_pvp_contracts
            WHERE player_id = ? AND day_key = ? AND contract_key = ?
            """,
            (player_id, day, contract.key),
        ).fetchone()
        if row is None or row[0] < contract.target:
            raise ContractClaimError(
                "That contract is not complete."
            )
        if row[1] is not None:
            raise ContractClaimError(
                "That contract reward was already claimed."
            )
        player = connection.execute(
            "SELECT xp FROM players WHERE id = ?",
            (player_id,),
        ).fetchone()
        if player is None:
            raise ContractClaimError("Player does not exist.")
        new_xp = player[0] + contract.xp_reward
        connection.execute(
            """
            UPDATE players
            SET money = money + ?, xp = ?, level = ?
            WHERE id = ?
            """,
            (
                contract.cash_reward,
                new_xp,
                level_for_xp(new_xp),
                player_id,
            ),
        )
        if contract.item_key is not None:
            connection.execute(
                """
                INSERT INTO player_inventory (
                    player_id, item_key, quantity
                )
                VALUES (?, ?, 1)
                ON CONFLICT(player_id, item_key)
                DO UPDATE SET quantity = quantity + 1
                """,
                (player_id, contract.item_key),
            )
        cursor = connection.execute(
            """
            UPDATE player_pvp_contracts
            SET claimed_at = ?, updated_at = ?
            WHERE player_id = ? AND day_key = ?
              AND contract_key = ? AND claimed_at IS NULL
            """,
            (
                now.isoformat(), now.isoformat(),
                player_id, day, contract.key,
            ),
        )
        if cursor.rowcount != 1:
            raise ContractClaimError(
                "That reward has already been claimed."
            )
        connection.commit()
        return ContractClaim(
            contract_name=contract.name,
            cash_reward=contract.cash_reward,
            xp_reward=contract.xp_reward,
            item_key=contract.item_key,
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _progress_amount(contract, result, approach):
    if contract.metric == "attempts":
        return 1
    if contract.metric == "wins":
        return 1 if result.victory else 0
    if contract.metric == "cash":
        return _cash_taken(result)
    if contract.metric == "approach_wins":
        # No approach means a street fight, which cannot satisfy these.
        return (
            1
            if result.victory
            and approach is not None
            and approach == contract.required_approach
            else 0
        )
    return 0


def _cash_taken(result):
    """What the player walked away with, whichever fight this was.

    A player fight reports `cash_stolen` and a street fight reports
    `cash_reward`. The contract does not care which pocket it came out
    of, so read whichever the result carries.
    """
    for field in ("cash_stolen", "cash_reward"):
        amount = getattr(result, field, None)
        if amount is not None:
            return max(0, amount)
    return 0


def _now(now):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)
