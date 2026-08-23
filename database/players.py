from datetime import datetime, timezone

from database.connection import get_connection
from game.regeneration import (
    ENERGY_POINTS_PER_TICK,
    ENERGY_TICK_SECONDS,
    NERVE_POINTS_PER_TICK,
    NERVE_TICK_SECONDS,
    regenerate_resource,
)


def create_player(user_id, name):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO players (
            user_id,
            name,
            nerve,
            max_energy,
            max_nerve,
            last_energy_update,
            last_nerve_update
        )
        VALUES (?, ?, 20, 100, 20, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (user_id, name)
    )

    conn.commit()
    player_id = cursor.lastrowid
    conn.close()

    return player_id


def get_player_by_user_id(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            user_id,
            name,
            level,
            money,
            health,
            energy,
            strength,
            defence,
            speed,
            dexterity,
            nerve,
            max_energy,
            max_nerve,
            last_energy_update,
            last_nerve_update,
            xp,
            wanted_level,
            last_wanted_update,
            jail_until,
            hospital_until,
            bank_balance,
            current_district,
            travel_destination,
            travel_until,
            residence_key
        FROM players
        WHERE user_id = ?
        """,
        (user_id,)
    )

    player_data = cursor.fetchone()

    if player_data is None:
        conn.close()
        return None

    player_data = list(player_data)
    now = datetime.now(timezone.utc)

    energy, energy_update = regenerate_resource(
        current_value=player_data[6],
        maximum_value=player_data[12],
        last_update=player_data[14],
        points_per_tick=ENERGY_POINTS_PER_TICK,
        tick_seconds=ENERGY_TICK_SECONDS,
        now=now
    )

    nerve, nerve_update = regenerate_resource(
        current_value=player_data[11],
        maximum_value=player_data[13],
        last_update=player_data[15],
        points_per_tick=NERVE_POINTS_PER_TICK,
        tick_seconds=NERVE_TICK_SECONDS,
        now=now
    )

    cursor.execute(
        """
        UPDATE players
        SET
            energy = ?,
            nerve = ?,
            last_energy_update = ?,
            last_nerve_update = ?
        WHERE id = ?
        """,
        (
            energy,
            nerve,
            energy_update,
            nerve_update,
            player_data[0]
        )
    )

    conn.commit()

    cursor.execute(
        """
        SELECT crime_key, xp, attempts, successes
        FROM player_crime_progress
        WHERE player_id = ?
        """,
        (player_data[0],)
    )
    crime_progress = {
        crime_key: {
            "xp": xp,
            "attempts": attempts,
            "successes": successes,
        }
        for crime_key, xp, attempts, successes in cursor.fetchall()
    }

    cursor.execute(
        """
        SELECT district, reputation
        FROM player_district_reputation
        WHERE player_id = ?
        """,
        (player_data[0],)
    )
    district_reputation = dict(cursor.fetchall())

    conn.close()

    player_data[6] = energy
    player_data[11] = nerve
    player_data[14] = energy_update
    player_data[15] = nerve_update

    player_data.extend([crime_progress, district_reputation])

    return tuple(player_data)


def save_player(player):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE players
        SET
            name = ?,
            level = ?,
            money = ?,
            bank_balance = ?,
            health = ?,
            energy = ?,
            strength = ?,
            defence = ?,
            speed = ?,
            dexterity = ?,
            nerve = ?,
            max_energy = ?,
            max_nerve = ?,
            last_energy_update = ?,
            last_nerve_update = ?,
            xp = ?,
            wanted_level = ?,
            last_wanted_update = ?,
            jail_until = ?,
            hospital_until = ?,
            current_district = ?,
            travel_destination = ?,
            travel_until = ?,
            residence_key = ?
        WHERE id = ?
        """,
        (
            player.name,
            player.level,
            player.money,
            player.bank_balance,
            player.health,
            player.energy,
            player.strength,
            player.defence,
            player.speed,
            player.dexterity,
            player.nerve,
            player.max_energy,
            player.max_nerve,
            player.last_energy_update,
            player.last_nerve_update,
            player.xp,
            player.wanted_level,
            player.last_wanted_update,
            player.jail_until,
            player.hospital_until,
            player.current_district,
            player.travel_destination,
            player.travel_until,
            player.residence_key,
            player.id
        )
    )

    cursor.execute(
        "DELETE FROM player_crime_progress WHERE player_id = ?",
        (player.id,)
    )
    cursor.executemany(
        """
        INSERT INTO player_crime_progress (
            player_id,
            crime_key,
            xp,
            attempts,
            successes
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                player.id,
                crime_key,
                progress["xp"],
                progress["attempts"],
                progress["successes"],
            )
            for crime_key, progress in player.crime_progress.items()
        ]
    )

    cursor.execute(
        "DELETE FROM player_district_reputation WHERE player_id = ?",
        (player.id,)
    )
    cursor.executemany(
        """
        INSERT INTO player_district_reputation (
            player_id,
            district,
            reputation
        )
        VALUES (?, ?, ?)
        """,
        [
            (player.id, district, reputation)
            for district, reputation
            in player.district_reputation.items()
        ]
    )

    conn.commit()
    conn.close()
