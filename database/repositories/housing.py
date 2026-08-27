"""Buying a home, and fitting it out.

Both of these move money, so both follow the rule the rest of the game
follows: the balance is read and debited inside one `BEGIN IMMEDIATE`
transaction, keyed on the stored row rather than on a Player object
handed in by the caller.

That distinction is the whole point. A Player is a snapshot taken when
the request began. Checking `player.money` and then writing the purchase
separately lets two requests each approve a purchase the other has
already spent the money on, and leaves a window where the goods are
committed but the payment is not.
"""

import sqlite3
from datetime import datetime, timezone

from database.core.connection import get_connection
from game.housing.service import (
    HousingError,
    InsufficientCashError,
    UnknownResidenceError,
    daily_upkeep,
    facility_for,
    get_residence,
    upkeep_owed,
)


def _spend(connection, player_id, amount):
    """Take the price from the stored balance, or refuse.

    One statement, so the balance cannot go stale between being checked
    and being charged.
    """
    charged = connection.execute(
        """
        UPDATE players
        SET money = money - ?
        WHERE id = ? AND money >= ?
        """,
        (amount, player_id, amount),
    ).rowcount

    if charged != 1:
        raise InsufficientCashError("Not enough carried cash.")

    return connection.execute(
        "SELECT money FROM players WHERE id = ?",
        (player_id,),
    ).fetchone()[0]


def _player(connection, user_id):
    row = connection.execute(
        "SELECT id, residence_key FROM players WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if row is None:
        raise HousingError("Player not found.")

    return row


def facilities_for(user_id):
    """Every facility this player has installed."""
    connection = get_connection()

    try:
        return {
            row[0]
            for row in connection.execute(
                """
                SELECT f.facility_key
                FROM player_housing_facilities f
                JOIN players p ON p.id = f.player_id
                WHERE p.user_id = ?
                """,
                (user_id,),
            )
        }
    finally:
        connection.close()


def install_facility(user_id, facility_key):
    """Fit a facility and pay for it, together or not at all.

    Returns the definition and the balance left afterwards.
    """
    name, price, effect = facility_for(facility_key)
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, _residence_key = _player(connection, user_id)

        already = connection.execute(
            """
            SELECT 1
            FROM player_housing_facilities
            WHERE player_id = ? AND facility_key = ?
            """,
            (player_id, facility_key),
        ).fetchone()

        if already:
            raise HousingError("Facility already installed.")

        remaining = _spend(connection, player_id, price)
        connection.execute(
            """
            INSERT INTO player_housing_facilities
                (player_id, facility_key)
            VALUES (?, ?)
            """,
            (player_id, facility_key),
        )
        connection.commit()
        return (name, price, effect), remaining
    except (HousingError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


def move_house(user_id, residence_key):
    """Buy a residence and move into it in one transaction.

    Returns the residence and the balance left afterwards.
    """
    residence = get_residence(residence_key)

    if residence is None:
        raise UnknownResidenceError("Residence does not exist.")

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, current = _player(connection, user_id)

        if current == residence.key:
            raise HousingError("You already live at this residence.")

        remaining = _spend(
            connection,
            player_id,
            residence.purchase_price,
        )
        connection.execute(
            "UPDATE players SET residence_key = ? WHERE id = ?",
            (residence.key, player_id),
        )
        connection.commit()
        return residence, remaining
    except (HousingError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


TIMESTAMP = "%Y-%m-%d %H:%M:%S"


def _now():
    return datetime.now(timezone.utc)


def _stamp(moment):
    return moment.strftime(TIMESTAMP)


def _read_stamp(text):
    if not text:
        return None

    parsed = datetime.fromisoformat(str(text).replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def _settle(connection, player_id, residence_key, now):
    """Bring the rent up to date and return what is outstanding.

    Lazy accrual, the same way the loan shark and every resource clock
    work: nothing is scheduled, the bill is simply worked out from when
    it was last settled.
    """
    residence = get_residence(residence_key)

    if daily_upkeep(residence) <= 0:
        # A free home. Clear any record so moving down the ladder does
        # not leave a bill behind for somewhere they no longer live.
        connection.execute(
            "DELETE FROM player_housing_upkeep WHERE player_id = ?",
            (player_id,),
        )
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
        connection.execute(
            """
            INSERT INTO player_housing_upkeep (player_id, settled_at)
            VALUES (?, ?)
            """,
            (player_id, _stamp(now)),
        )
        return 0

    settled_at, arrears = row
    accrued = upkeep_owed(residence, now - _read_stamp(settled_at))
    total = arrears + accrued

    connection.execute(
        """
        UPDATE player_housing_upkeep
        SET settled_at = ?, arrears = ?
        WHERE player_id = ?
        """,
        (_stamp(now), total, player_id),
    )

    return total


def upkeep_for(user_id):
    """What this player owes on their home right now."""
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, residence_key FROM players WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            connection.rollback()
            return {"owed": 0, "daily": 0, "in_arrears": False}

        player_id, residence_key = row
        owed = _settle(connection, player_id, residence_key, _now())
        connection.commit()

        return {
            "owed": owed,
            "daily": daily_upkeep(get_residence(residence_key)),
            "in_arrears": owed > 0,
        }
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def pay_upkeep(user_id, amount=None):
    """Clear the rent, or as much of it as the player asks to.

    Returns what was actually taken and what is left owing.
    """
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT id, residence_key, money
            FROM players WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if row is None:
            raise HousingError("Player not found.")

        player_id, residence_key, money = row
        owed = _settle(connection, player_id, residence_key, _now())

        if owed <= 0:
            raise HousingError("You are straight with the landlord.")

        paying = owed if amount is None else min(int(amount), owed)

        if paying < 1:
            raise HousingError("Pay something.")

        if paying > money:
            raise InsufficientCashError("Not enough carried cash.")

        connection.execute(
            "UPDATE players SET money = money - ? WHERE id = ?",
            (paying, player_id),
        )
        connection.execute(
            "UPDATE player_housing_upkeep SET arrears = ? WHERE player_id = ?",
            (owed - paying, player_id),
        )
        connection.commit()

        return paying, owed - paying
    except (HousingError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()
