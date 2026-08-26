"""The loan book.

Rules live in `game.economy.loans`; this runs them inside a transaction
so a debt cannot be borrowed against or repaid twice from two tabs.

Interest accrues lazily on read, from elapsed time, the same way energy
and nerve do -- so a loan costs what it should whether or not the player
was logged in while it was running.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from database.core.connection import get_connection
from game.economy.loans import (
    PAYMENT_PERIOD,
    Loan,
    LoanError,
    apply_repayment,
    clears_arrears,
    headroom,
    hospital_minutes,
    interest_for,
    maximum_loan,
    validate_borrow,
    validate_repayment,
)


LOAN_DISTRICT = "soho"


def _utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse(value):
    """Read a stored timestamp as an aware UTC datetime.

    Everything this project stores is UTC, but not everything writes the
    offset -- a value from SQLite's own `datetime()` has none. Treating a
    naive timestamp as UTC keeps that from becoming a crash on the
    subtraction.
    """
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _format(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_row(connection, player_id):
    return connection.execute(
        """
        SELECT principal, interest, missed_payments,
               taken_at, interest_accrued_at, due_at
        FROM player_loans
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()


def _accrue(connection, player_id, row, now):
    """Bring interest up to date. Returns (loan, due_at)."""
    if row is None:
        return Loan(principal=0, interest=0), None

    principal, interest, missed, _taken, accrued_at, due_at = row
    since = _parse(accrued_at)

    if principal > 0 and since is not None:
        earned = interest_for(principal, now - since)
        if earned > 0:
            interest += earned
            connection.execute(
                """
                UPDATE player_loans
                SET interest = ?, interest_accrued_at = ?
                WHERE player_id = ?
                """,
                (interest, _format(now), player_id),
            )
            connection.execute(
                """
                INSERT INTO loan_transactions
                    (player_id, kind, amount, balance_after)
                VALUES (?, 'interest', ?, ?)
                """,
                (player_id, earned, principal + interest),
            )
    return Loan(principal, interest, missed), _parse(due_at)


def _player(connection, user_id, at_the_office=True):
    row = connection.execute(
        """
        SELECT id, level, money, current_district, travel_destination,
               jail_until, hospital_until
        FROM players
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    if row is None:
        raise LoanError("Player not found.")

    player_id, level, money, district, travelling, jail, hospital = row

    if at_the_office:
        if district != LOAN_DISTRICT:
            raise LoanError("Ronnie works out of the back of a Soho pub.")
        if travelling:
            raise LoanError("You cannot do business while travelling.")
        if jail or hospital:
            raise LoanError("You are in no state to be doing business.")

    return player_id, level, money


def get_loan(user_id):
    """The loan as it stands, with interest brought up to date."""
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, level FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None

        player_id, level = row
        now = _utcnow()
        loan, due_at = _accrue(connection, player_id, _read_row(connection, player_id), now)
        connection.commit()
        return {
            "loan": loan,
            "due_at": due_at,
            "overdue": bool(due_at and loan.principal > 0 and now > due_at),
            "maximum": maximum_loan(level),
            "headroom": headroom(level, loan.principal),
        }
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def borrow(user_id, amount):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, level, _money = _player(connection, user_id)
        now = _utcnow()
        loan, due_at = _accrue(
            connection, player_id, _read_row(connection, player_id), now
        )

        if loan.interest > 0:
            raise LoanError(
                "Clear what you owe him in interest before asking for more."
            )
        amount = validate_borrow(level, amount, loan.principal)

        principal = loan.principal + amount
        # An existing loan keeps its deadline; a new one starts the clock.
        deadline = due_at if loan.principal else now + PAYMENT_PERIOD

        connection.execute(
            """
            INSERT INTO player_loans
                (player_id, principal, interest, missed_payments,
                 taken_at, interest_accrued_at, due_at)
            VALUES (?, ?, 0, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                principal = excluded.principal,
                interest_accrued_at = excluded.interest_accrued_at,
                due_at = excluded.due_at
            """,
            (
                player_id, principal, loan.missed_payments,
                _format(now), _format(now), _format(deadline),
            ),
        )
        connection.execute(
            "UPDATE players SET money = money + ? WHERE id = ?",
            (amount, player_id),
        )
        connection.execute(
            """
            INSERT INTO loan_transactions
                (player_id, kind, amount, balance_after)
            VALUES (?, 'borrow', ?, ?)
            """,
            (player_id, amount, principal),
        )
        connection.commit()
        return amount, principal
    except (LoanError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


def repay(user_id, amount):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        # A debt can be paid from anywhere. Making someone travel to Soho
        # to stop the interest would be a trap, not a mechanic.
        player_id, _level, money = _player(connection, user_id, at_the_office=False)
        now = _utcnow()
        loan, due_at = _accrue(
            connection, player_id, _read_row(connection, player_id), now
        )

        amount = validate_repayment(amount, loan.balance, money)
        cleared = clears_arrears(loan, amount)
        after = apply_repayment(loan, amount)

        deadline = due_at
        if cleared:
            deadline = now + PAYMENT_PERIOD
        if after.settled:
            deadline = None

        connection.execute(
            """
            UPDATE player_loans
            SET principal = ?, interest = ?, interest_accrued_at = ?, due_at = ?
            WHERE player_id = ?
            """,
            (
                after.principal, after.interest, _format(now),
                _format(deadline) if deadline else None,
                player_id,
            ),
        )
        connection.execute(
            "UPDATE players SET money = money - ? WHERE id = ?",
            (amount, player_id),
        )
        connection.execute(
            """
            INSERT INTO loan_transactions
                (player_id, kind, amount, balance_after)
            VALUES (?, 'repay', ?, ?)
            """,
            (player_id, amount, after.balance),
        )
        connection.commit()
        return amount, after
    except (LoanError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


def collect_if_overdue(user_id, now=None):
    """Ronnie's people catch up with a late payer.

    Called on every request for a signed-in player, so a debt cannot be
    dodged by staying off the loan shark's page. Returns the hospital
    stay in minutes when a collection happened, otherwise None.
    """
    now = now or _utcnow()
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT p.id, l.principal, l.interest, l.missed_payments,
                   l.due_at, p.hospital_until
            FROM players p
            JOIN player_loans l ON l.player_id = p.id
            WHERE p.user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if row is None:
            connection.commit()
            return None

        player_id, principal, interest, missed, due_at, hospital_until = row
        deadline = _parse(due_at)

        if principal <= 0 or deadline is None or now <= deadline:
            connection.commit()
            return None

        minutes = hospital_minutes(missed)
        release = now + timedelta(minutes=minutes)
        existing = _parse(hospital_until)
        # Never shorten a stay the player is already serving.
        if existing and existing > release:
            release = existing

        connection.execute(
            """
            UPDATE player_loans
            SET missed_payments = missed_payments + 1, due_at = ?
            WHERE player_id = ?
            """,
            (_format(now + PAYMENT_PERIOD), player_id),
        )
        connection.execute(
            "UPDATE players SET hospital_until = ? WHERE id = ?",
            (_format(release), player_id),
        )
        connection.execute(
            """
            INSERT INTO loan_transactions
                (player_id, kind, amount, balance_after)
            VALUES (?, 'collection', ?, ?)
            """,
            (player_id, minutes, principal + interest),
        )
        connection.commit()
        return minutes
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def recent_transactions(user_id, limit=10):
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT t.kind, t.amount, t.balance_after, t.happened_at
            FROM loan_transactions t
            JOIN players p ON p.id = t.player_id
            WHERE p.user_id = ?
            ORDER BY t.id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    finally:
        connection.close()
