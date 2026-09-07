"""The facts the dashboard panel needs, read without moving anything.

Every one of these numbers already exists somewhere, and every existing
way of getting it settles a clock: `upkeep_for` moves the rent marker,
`get_loan` accrues interest, `get_contract_board` rolls the board. All
three open `BEGIN IMMEDIATE`, which is right where they are used and
wrong here -- this runs on the busiest page in the game, the one every
session starts on.

So these are read-only twins. `database.repositories.players._rent_owed`
established the pattern and says why: the figure is exact without the
marker moving, and the marker is only worth moving when somebody is
actually looking at that page or paying.

Nothing here writes. If a function in this module ever needs a
transaction, it belongs in the module that owns the mechanic instead.
"""

from datetime import datetime, timezone

from database.core.connection import get_connection
from game.economy.loans import interest_for
from game.housing.service import daily_upkeep, get_residence, upkeep_owed
from game.player.regeneration import parse_timestamp


def _now(now=None):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _moment(value):
    stamp = parse_timestamp(value) if value else None

    if stamp is None:
        return None

    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def facts_for(player, now=None):
    """Everything the digest needs, in one connection.

    One connection and four small indexed reads rather than four
    connections: this is the landing page, and the cost of it is paid
    by every session in the game.
    """
    now = _now(now)
    residence = get_residence(getattr(player, "residence_key", None))
    connection = get_connection()

    try:
        return {
            "rent_owed": _rent_owed(
                connection, player.id, residence, now
            ),
            "daily_rent": daily_upkeep(residence) if residence else 0,
            **_loan(connection, player.id, now),
            "notifications": _notifications(connection, player.id),
        }
    finally:
        connection.close()


def _rent_owed(connection, player_id, residence, now):
    """Stored arrears plus whatever has accrued since, marker untouched.

    Deliberately the same arithmetic the player loader already runs to
    decide whether the home is suspended -- if these two ever disagree,
    the panel would be announcing a debt the game is not charging, or
    staying quiet about one it is.
    """
    if residence is None or daily_upkeep(residence) <= 0:
        return 0

    row = connection.execute(
        """
        SELECT settled_at, arrears
        FROM player_housing_upkeep
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()

    if row is None:
        return 0

    settled_at, arrears = row
    settled = _moment(settled_at)

    if settled is None:
        return arrears

    return arrears + upkeep_owed(residence, now - settled)


def _loan(connection, player_id, now):
    """What is owed and whether the payment has been missed."""
    row = connection.execute(
        """
        SELECT principal, interest, missed_payments,
               interest_accrued_at, due_at
        FROM player_loans
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()

    if row is None:
        return {
            "loan_balance": 0,
            "loan_overdue": False,
            "missed_payments": 0,
        }

    principal, interest, missed, accrued_at, due_at = row

    if principal <= 0:
        return {
            "loan_balance": 0,
            "loan_overdue": False,
            "missed_payments": missed or 0,
        }

    since = _moment(accrued_at)

    if since is not None:
        interest += interest_for(principal, now - since)

    due = _moment(due_at)

    return {
        "loan_balance": principal + interest,
        "loan_overdue": due is not None and due <= now,
        "missed_payments": missed or 0,
    }


def _notifications(connection, player_id, limit=10):
    """Unread messages, left unread.

    The dashboard is the alert and `/pvp` is the inbox: reading the
    panel must not consume the thing it is pointing at, or a player who
    glances at the dashboard loses the detail for ever.
    """
    rows = connection.execute(
        """
        SELECT message FROM pvp_notifications
        WHERE player_id = ? AND read_at IS NULL
        ORDER BY id DESC LIMIT ?
        """,
        (player_id, limit),
    ).fetchall()

    return tuple(row[0] for row in rows)
