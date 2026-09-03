"""Who the machines are, and the key each one plays with.

Pure rules live in `game/agents/`; this is the part that remembers.

A key is shown once and stored only as a SHA-256 hash, the same way the
password reset tokens are. There is no recovery path on purpose: a lost
key is reissued, never retrieved.

`is_agent` is read on every player-versus-player interaction in the
game, so it is one indexed lookup and no transaction.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from database.core.connection import get_connection
from game.agents.service import (
    AgentError,
    generate_key,
    looks_like_key,
    sealed_reason,
)
from game.player.regeneration import format_timestamp
from utils.security import hash_token


@dataclass(frozen=True)
class AgentAccount:
    user_id: int
    player_id: int
    name: str
    label: str
    calls: int
    created_at: str
    last_used_at: str | None


def _now(now=None):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def issue_key(user_id, label, now=None):
    """Make this account an agent and hand back its one and only key.

    Re-issuing replaces the previous key rather than adding a second,
    so an account has exactly one live credential and revoking is
    unambiguous.
    """
    label = (label or "").strip()

    if not label:
        raise AgentError("Give the agent a name.")

    if len(label) > 60:
        raise AgentError("That name is too long.")

    now = _now(now)
    raw = generate_key()

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        exists = connection.execute(
            "SELECT 1 FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()

        if exists is None:
            raise AgentError("That account has no character.")

        connection.execute(
            "DELETE FROM agent_keys WHERE user_id = ?", (user_id,)
        )
        connection.execute(
            """
            INSERT INTO agent_keys (
                user_id, key_hash, label, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (user_id, hash_token(raw), label, format_timestamp(now)),
        )
        connection.commit()
        return raw
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def revoke_key(user_id, now=None):
    """Stop a key working, and stop the account being an agent.

    Marked rather than deleted, so the account keeps its history and
    stays visibly a former machine rather than quietly rejoining the
    human leaderboard.
    """
    now = _now(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        changed = connection.execute(
            "UPDATE agent_keys SET revoked_at = ? "
            "WHERE user_id = ? AND revoked_at IS NULL",
            (format_timestamp(now), user_id),
        ).rowcount
        connection.commit()
        return changed == 1
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def authenticate(raw_key, now=None):
    """The account behind a key, or None.

    Records the call as it goes, which is both the audit trail and the
    only way to tell a working agent from an abandoned one.
    """
    if not looks_like_key(raw_key):
        return None

    now = _now(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT agent_keys.user_id, players.id, players.name,
                   agent_keys.label, agent_keys.calls,
                   agent_keys.created_at, agent_keys.last_used_at
            FROM agent_keys
            JOIN players ON players.user_id = agent_keys.user_id
            WHERE agent_keys.key_hash = ?
              AND agent_keys.revoked_at IS NULL
            """,
            (hash_token(raw_key),),
        ).fetchone()

        if row is None:
            connection.commit()
            return None

        connection.execute(
            "UPDATE agent_keys SET calls = calls + 1, last_used_at = ? "
            "WHERE user_id = ?",
            (format_timestamp(now), row[0]),
        )
        connection.commit()

        return AgentAccount(
            user_id=row[0],
            player_id=row[1],
            name=row[2],
            label=row[3],
            calls=row[4] + 1,
            created_at=row[5],
            last_used_at=row[6],
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def is_agent(player_id):
    """Whether this player is a machine.

    Read on every interaction that moves value between two players, in
    both directions, so it stays a single indexed row.
    """
    if player_id is None:
        return False

    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT 1 FROM agent_keys
            JOIN players ON players.user_id = agent_keys.user_id
            WHERE players.id = ? AND agent_keys.revoked_at IS NULL
            """,
            (player_id,),
        ).fetchone()
    finally:
        connection.close()

    return row is not None


def _is_agent_on(connection, player_id):
    if player_id is None:
        return False

    return connection.execute(
        """
        SELECT 1 FROM agent_keys
        JOIN players ON players.user_id = agent_keys.user_id
        WHERE players.id = ? AND agent_keys.revoked_at IS NULL
        """,
        (player_id,),
    ).fetchone() is not None


def refuse_if_sealed(connection, action, actor_id, target_id=None):
    """The wall, checked on the caller's own connection.

    Every mechanic that moves value between two players calls this, on
    the transaction that is about to do the moving -- so the check and
    the write cannot disagree, and an agent cannot slip through by
    coming in via the web session instead of the API.

    Raises rather than returning, because there is no sensible partial
    answer: the interaction happens or it does not.
    """
    reason = sealed_reason(
        action,
        _is_agent_on(connection, actor_id),
        _is_agent_on(connection, target_id),
    )

    if reason is not None:
        raise AgentError(reason)


def agent_player_ids():
    """Every machine, for the places that list players in bulk."""
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT players.id FROM agent_keys
            JOIN players ON players.user_id = agent_keys.user_id
            WHERE agent_keys.revoked_at IS NULL
            """
        ).fetchall()
    finally:
        connection.close()

    return {row[0] for row in rows}


def roster(limit=50):
    """The agents on the server, for their own leaderboard."""
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT players.id, players.name, agent_keys.label,
                   players.level, players.xp, agent_keys.calls,
                   agent_keys.last_used_at
            FROM agent_keys
            JOIN players ON players.user_id = agent_keys.user_id
            WHERE agent_keys.revoked_at IS NULL
            ORDER BY players.xp DESC, players.name COLLATE NOCASE ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "player_id": row[0],
            "name": row[1],
            "label": row[2],
            "level": row[3],
            "xp": row[4],
            "calls": row[5],
            "last_seen": row[6],
        }
        for row in rows
    ]
