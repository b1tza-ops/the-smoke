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

from database.core.connection import get_connection
from game.housing.service import (
    HousingError,
    InsufficientCashError,
    UnknownResidenceError,
    facility_for,
    get_residence,
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
