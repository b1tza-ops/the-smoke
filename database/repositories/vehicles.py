"""The garage.

Pure rules live in `game/vehicles/`; this is the part that remembers
what somebody owns, takes the money for it, and makes sure exactly one
vehicle is the one they are driving.

Every write runs inside BEGIN IMMEDIATE and re-reads under the write
lock. Buying is the obvious place to get two cars for one payment, and
a double-submitted form is exactly what a refresh does.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from database.core.connection import get_connection
from game.vehicles.definitions import get_vehicle
from game.vehicles.service import (
    VehicleError,
    garage_capacity,
    garage_room,
    resale_value,
    validate_purchase,
)
from game.player.regeneration import format_timestamp


# Coldharbour Lane, Brixton. Level 1, so a car is reachable from the
# first hour if somebody saves for the van to keep it in.
FORECOURT_DISTRICT = "brixton"


@dataclass(frozen=True)
class OwnedVehicle:
    id: int
    vehicle: object
    active: bool


@dataclass(frozen=True)
class Garage:
    vehicles: tuple
    capacity: int
    room: int

    @property
    def active(self):
        return next(
            (owned for owned in self.vehicles if owned.active), None
        )

    @property
    def empty(self):
        return not self.vehicles


def _now(now=None):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _player(connection, user_id):
    row = connection.execute(
        """
        SELECT id, money, level, residence_key,
               current_district, travel_destination
        FROM players WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    if row is None:
        raise VehicleError("You do not have a character yet.")

    return row


def _require_forecourt(row):
    """Money only changes hands on the forecourt.

    Enforced here rather than in the template, because the template is
    a suggestion and this is the thing that moves the money. A car is
    bought and sold in Brixton; what you already own you can pick
    between from anywhere, since the garage is at home.
    """
    if row[5] is not None:
        raise VehicleError("You are in the middle of a journey.")

    if row[4] != FORECOURT_DISTRICT:
        raise VehicleError(
            "Coldharbour Motors is in Brixton. You are not."
        )


def _owned(connection, player_id):
    rows = connection.execute(
        """
        SELECT id, vehicle_key, is_active
        FROM player_vehicles
        WHERE player_id = ?
        ORDER BY id ASC
        """,
        (player_id,),
    ).fetchall()

    return tuple(
        OwnedVehicle(
            id=row[0],
            vehicle=get_vehicle(row[1]),
            active=bool(row[2]),
        )
        for row in rows
        # A key the catalogue no longer knows is skipped rather than
        # rendered as a hole. Nothing removes vehicles today, but a
        # retired model should not break the page for whoever owns it.
        if get_vehicle(row[1]) is not None
    )


def garage_for(user_id):
    """Everything owned, with the room left to own more."""
    connection = get_connection()
    try:
        row = _player(connection, user_id)
        player_id, residence_key = row[0], row[3]
        vehicles = _owned(connection, player_id)
    finally:
        connection.close()

    return Garage(
        vehicles=vehicles,
        capacity=garage_capacity(residence_key),
        room=garage_room(residence_key, len(vehicles)),
    )


def active_vehicle(player_id):
    """What this player would be driving, or None.

    Read by the travel page on every load, so it is one indexed row and
    no transaction.
    """
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT vehicle_key FROM player_vehicles
            WHERE player_id = ? AND is_active = 1
            """,
            (player_id,),
        ).fetchone()
    finally:
        connection.close()

    return get_vehicle(row[0]) if row else None


def owned_count(player_id):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM player_vehicles WHERE player_id = ?",
            (player_id,),
        ).fetchone()
    finally:
        connection.close()

    return row[0]


def buy_vehicle(user_id, vehicle_key, now=None):
    """Take the money and put it on the drive.

    The first vehicle somebody buys becomes the active one, because a
    garage with one car in it and nothing selected is a page that looks
    broken.
    """
    now = _now(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _player(connection, user_id)
        _require_forecourt(row)
        player_id, money, level, residence_key = row[:4]
        owned = _owned(connection, player_id)

        vehicle = validate_purchase(
            vehicle_key, level, money, residence_key, len(owned)
        )

        paid = connection.execute(
            "UPDATE players SET money = money - ? "
            "WHERE id = ? AND money >= ?",
            (vehicle.price, player_id, vehicle.price),
        ).rowcount

        if paid != 1:
            raise VehicleError("You cannot afford that.")

        connection.execute(
            """
            INSERT INTO player_vehicles (
                player_id, vehicle_key, is_active, purchased_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                player_id,
                vehicle.key,
                0 if owned else 1,
                format_timestamp(now),
            ),
        )
        connection.commit()

        return vehicle
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def sell_vehicle(user_id, owned_id):
    """Sell one back to the forecourt for half what it cost."""
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        owner = _player(connection, user_id)
        _require_forecourt(owner)
        player_id = owner[0]

        row = connection.execute(
            """
            SELECT vehicle_key FROM player_vehicles
            WHERE id = ? AND player_id = ?
            """,
            (owned_id, player_id),
        ).fetchone()

        if row is None:
            raise VehicleError("That is not in your garage.")

        vehicle = get_vehicle(row[0])

        if vehicle is None:
            raise VehicleError("Nobody will take that off you.")

        removed = connection.execute(
            "DELETE FROM player_vehicles WHERE id = ? AND player_id = ?",
            (owned_id, player_id),
        ).rowcount

        if removed != 1:
            # Sold by a request that got here first.
            raise VehicleError("That is not in your garage.")

        paid = resale_value(vehicle)
        connection.execute(
            "UPDATE players SET money = money + ? WHERE id = ?",
            (paid, player_id),
        )

        # Selling the car you were driving leaves nothing selected, so
        # the next one along takes over rather than the travel page
        # quietly losing its drive option.
        _promote_if_none_active(connection, player_id)
        connection.commit()

        return vehicle, paid
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _promote_if_none_active(connection, player_id):
    active = connection.execute(
        """
        SELECT COUNT(*) FROM player_vehicles
        WHERE player_id = ? AND is_active = 1
        """,
        (player_id,),
    ).fetchone()[0]

    if active:
        return

    connection.execute(
        """
        UPDATE player_vehicles SET is_active = 1
        WHERE id = (
            SELECT id FROM player_vehicles
            WHERE player_id = ? ORDER BY id ASC LIMIT 1
        )
        """,
        (player_id,),
    )


def set_active(user_id, owned_id):
    """Choose which one you are driving.

    Cleared first and set second, in one transaction: the partial
    unique index refuses two active rows, so doing it the other way
    round would fail on the write rather than on the intent.
    """
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id = _player(connection, user_id)[0]

        owns = connection.execute(
            """
            SELECT COUNT(*) FROM player_vehicles
            WHERE id = ? AND player_id = ?
            """,
            (owned_id, player_id),
        ).fetchone()[0]

        if not owns:
            raise VehicleError("That is not in your garage.")

        connection.execute(
            "UPDATE player_vehicles SET is_active = 0 WHERE player_id = ?",
            (player_id,),
        )
        connection.execute(
            "UPDATE player_vehicles SET is_active = 1 "
            "WHERE id = ? AND player_id = ?",
            (owned_id, player_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
