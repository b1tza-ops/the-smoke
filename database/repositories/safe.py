"""The safe, and the people who come for it.

Pure rules live in `game/housing/safe.py` and `game/crime/burglary.py`;
this is the part that remembers a balance, settles its interest, and
moves money between two players without either of them being able to
make it happen twice.

Every write runs inside BEGIN IMMEDIATE and re-reads under the write
lock. A double-submitted burglary is the obvious way to rob a house
twice for one lot of nerve, and it is exactly what a refresh does.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random

from database.core.connection import get_connection
from database.repositories.agents import refuse_if_sealed
from game.crime.burglary import (
    BURGLARY_COOLDOWN_SECONDS,
    BURGLARY_JAIL_CHANCE,
    BURGLARY_JAIL_SECONDS,
    BURGLARY_NERVE_COST,
    BurglaryError,
    odds_against,
    takings,
    worth_robbing,
)
from game.housing.safe import SafeError, capacity_for, interest_earned
from game.player.regeneration import format_timestamp, parse_timestamp


# The same window player fights use. Somebody's first three days should
# not be spent being robbed.
NEW_PLAYER_PROTECTION_HOURS = 72


@dataclass(frozen=True)
class SafeState:
    balance: int
    capacity: int
    interest_earned: int

    @property
    def room(self):
        return max(0, self.capacity - self.balance)

    @property
    def full(self):
        return self.balance >= self.capacity


@dataclass(frozen=True)
class Burglary:
    succeeded: bool
    taken: int
    victim_name: str
    chance: int
    jailed: bool
    jail_until: str | None = None


def _now(now=None):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _settle(connection, player_id, now):
    """Bring a safe's interest up to date and return the balance.

    Read-modify-write inside whatever transaction the caller opened, so
    interest can never be credited twice for the same stretch of time.
    """
    row = connection.execute(
        "SELECT balance, settled_at FROM player_safe WHERE player_id = ?",
        (player_id,),
    ).fetchone()

    if row is None:
        return 0, 0

    balance, settled_at = row
    since = parse_timestamp(settled_at)
    if since is None:
        earned = 0
    else:
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        earned = interest_earned(balance, now - since)

    if earned:
        balance += earned

    connection.execute(
        "UPDATE player_safe SET balance = ?, settled_at = ? "
        "WHERE player_id = ?",
        (balance, format_timestamp(now), player_id),
    )

    return balance, earned


def safe_for(user_id, now=None):
    """What is in the safe, with its interest brought up to date."""
    now = _now(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, residence_key FROM players WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise SafeError("No such player.")

        player_id, residence_key = row
        balance, earned = _settle(connection, player_id, now)
        connection.commit()

        return SafeState(
            balance=balance,
            capacity=capacity_for(residence_key),
            interest_earned=earned,
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def deposit(user_id, amount, now=None):
    """Move cash from pocket to safe."""
    amount = int(amount)
    if amount <= 0:
        raise SafeError("Enter an amount to put away.")

    now = _now(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, residence_key, money FROM players WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise SafeError("No such player.")

        player_id, residence_key, money = row
        capacity = capacity_for(residence_key)

        connection.execute(
            "INSERT OR IGNORE INTO player_safe (player_id, balance, settled_at)"
            " VALUES (?, 0, ?)",
            (player_id, format_timestamp(now)),
        )
        balance, _ = _settle(connection, player_id, now)

        if amount > money:
            raise SafeError("You are not carrying that much.")
        if balance + amount > capacity:
            raise SafeError(
                f"Your safe holds £{capacity:,}; "
                f"there is room for £{max(0, capacity - balance):,}."
            )

        connection.execute(
            "UPDATE players SET money = money - ? WHERE id = ? AND money >= ?",
            (amount, player_id, amount),
        )
        connection.execute(
            "UPDATE player_safe SET balance = balance + ? WHERE player_id = ?",
            (amount, player_id),
        )
        connection.commit()
        return balance + amount
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def withdraw(user_id, amount, now=None):
    """Take cash back out of the safe."""
    amount = int(amount)
    if amount <= 0:
        raise SafeError("Enter an amount to take out.")

    now = _now(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise SafeError("No such player.")

        player_id = row[0]
        balance, _ = _settle(connection, player_id, now)

        if amount > balance:
            raise SafeError("There is not that much in the safe.")

        connection.execute(
            "UPDATE player_safe SET balance = balance - ?"
            " WHERE player_id = ? AND balance >= ?",
            (amount, player_id, amount),
        )
        connection.execute(
            "UPDATE players SET money = money + ? WHERE id = ?",
            (amount, player_id),
        )
        connection.commit()
        return balance - amount
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# ---------------------------------------------------- breaking in
#
# Everything below is written so a burglary can fail safely. The order
# matters: charge the nerve, check the protections, roll, and only then
# move money -- all in one transaction, so a burglar who is refused
# pays nothing and a victim who is robbed loses exactly once.


def _protection_reason(connection, burglar_id, victim_id, now):
    """Why this house cannot be done over, or None if it can."""
    if burglar_id == victim_id:
        return "You live there."

    row = connection.execute(
        """
        SELECT users.created_at, players.hospital_until,
               players.jail_until
        FROM players
        JOIN users ON users.id = players.user_id
        WHERE players.id = ?
        """,
        (victim_id,),
    ).fetchone()
    if row is None:
        return "That player does not exist."

    created_at, hospital_until, jail_until = row
    joined = parse_timestamp(created_at)
    if joined is not None:
        if joined.tzinfo is None:
            joined = joined.replace(tzinfo=timezone.utc)
        protected_until = joined + timedelta(
            hours=NEW_PLAYER_PROTECTION_HOURS
        )
        if now < protected_until:
            return "They are still under new player protection."

    recent = connection.execute(
        """
        SELECT created_at FROM player_burglaries
        WHERE burglar_id = ? AND victim_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (burglar_id, victim_id),
    ).fetchone()
    if recent is not None:
        last = parse_timestamp(recent[0])
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            ready_at = last + timedelta(
                seconds=BURGLARY_COOLDOWN_SECONDS
            )
            if now < ready_at:
                minutes = int((ready_at - now).total_seconds() // 60) + 1
                return (
                    f"That house is still being watched. "
                    f"Try again in {minutes} minutes."
                )

    return None


def burgle(user_id, victim_player_id, rng=None, now=None):
    """Break into another player's home and empty part of their safe."""
    rng = rng or random.SystemRandom()
    now = _now(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        burglar = connection.execute(
            """
            SELECT id, nerve, jail_until, hospital_until,
                   travel_destination
            FROM players WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if burglar is None:
            raise BurglaryError("No such player.")

        burglar_id, nerve, jail_until, hospital_until, travelling = burglar

        # Checked on this transaction, before any nerve is spent: an
        # agent robs nobody and nobody robs an agent.
        refuse_if_sealed(
            connection, "burgle", burglar_id, victim_player_id
        )

        if jail_until:
            raise BurglaryError("You cannot do this from a cell.")
        if hospital_until:
            raise BurglaryError("You cannot do this from a hospital bed.")
        if travelling:
            raise BurglaryError("You cannot do this while travelling.")
        if nerve < BURGLARY_NERVE_COST:
            raise BurglaryError(
                f"You need {BURGLARY_NERVE_COST} nerve for that."
            )

        refusal = _protection_reason(
            connection, burglar_id, victim_player_id, now
        )
        if refusal:
            raise BurglaryError(refusal)

        victim = connection.execute(
            "SELECT name, residence_key FROM players WHERE id = ?",
            (victim_player_id,),
        ).fetchone()
        victim_name, victim_residence = victim

        victim_balance, _ = _settle(connection, victim_player_id, now)
        if not worth_robbing(victim_balance):
            raise BurglaryError(
                f"{victim_name} keeps nothing worth taking at home."
            )

        inventory = dict(connection.execute(
            "SELECT item_key, quantity FROM player_inventory"
            " WHERE player_id = ? AND quantity > 0",
            (burglar_id,),
        ))
        odds = odds_against(inventory, victim_residence)

        # The nerve goes whatever happens next.
        connection.execute(
            "UPDATE players SET nerve = nerve - ?"
            " WHERE id = ? AND nerve >= ?",
            (BURGLARY_NERVE_COST, burglar_id, BURGLARY_NERVE_COST),
        )

        succeeded = rng.randint(1, 100) <= odds.chance
        taken = 0
        jailed = False
        jail_until_stamp = None

        if succeeded:
            taken = min(takings(victim_balance), victim_balance)
            if taken:
                connection.execute(
                    "UPDATE player_safe SET balance = balance - ?"
                    " WHERE player_id = ? AND balance >= ?",
                    (taken, victim_player_id, taken),
                )
                connection.execute(
                    "UPDATE players SET money = money + ? WHERE id = ?",
                    (taken, burglar_id),
                )
            connection.execute(
                """
                INSERT INTO pvp_notifications (
                    player_id, attack_id, message, created_at
                ) VALUES (?, NULL, ?, ?)
                """,
                (
                    victim_player_id,
                    f"Your home was broken into. £{taken:,} "
                    f"was taken from your safe.",
                    now.isoformat(),
                ),
            )
        else:
            jailed = rng.randint(1, 100) <= BURGLARY_JAIL_CHANCE
            if jailed:
                until = now + timedelta(seconds=BURGLARY_JAIL_SECONDS)
                jail_until_stamp = format_timestamp(until)
                connection.execute(
                    "UPDATE players SET jail_until = ? WHERE id = ?",
                    (jail_until_stamp, burglar_id),
                )
            connection.execute(
                """
                INSERT INTO pvp_notifications (
                    player_id, attack_id, message, created_at
                ) VALUES (?, NULL, ?, ?)
                """,
                (
                    victim_player_id,
                    "Somebody tried to break into your home "
                    "and did not get in.",
                    now.isoformat(),
                ),
            )

        connection.execute(
            """
            INSERT INTO player_burglaries (
                burglar_id, victim_id, succeeded, taken, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                burglar_id, victim_player_id,
                1 if succeeded else 0, taken, format_timestamp(now),
            ),
        )
        connection.commit()

        return Burglary(
            succeeded=succeeded,
            taken=taken,
            victim_name=victim_name,
            chance=odds.chance,
            jailed=jailed,
            jail_until=jail_until_stamp,
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
