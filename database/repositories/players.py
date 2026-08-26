from datetime import datetime, timezone

from database.core.connection import get_connection
from game.player.regeneration import (
    ENERGY_POINTS_PER_TICK,
    ENERGY_TICK_SECONDS,
    HAPPINESS_POINTS_PER_TICK,
    HAPPINESS_TICK_SECONDS,
    HEALTH_POINTS_PER_TICK,
    HEALTH_TICK_SECONDS,
    NERVE_POINTS_PER_TICK,
    NERVE_TICK_SECONDS,
    parse_timestamp,
    regenerate_resource,
)


def create_player(user_id, name):
    conn = get_connection()
    cursor = conn.cursor()

    # Every regenerating resource gets its clock set here rather than
    # left to a column default. The two shapes this table can have do
    # not agree: a database built fresh from the CREATE TABLE declares
    # these NOT NULL DEFAULT CURRENT_TIMESTAMP, while one upgraded
    # through the migrations got them from ALTER TABLE, which cannot
    # carry a non-constant default and so left them plain nullable TEXT.
    # On the upgraded shape a new player was written with NULL clocks
    # and the loader raised on the first page they opened.
    cursor.execute(
        """
        INSERT INTO players (
            user_id,
            name,
            energy,
            nerve,
            max_energy,
            max_nerve,
            last_energy_update,
            last_nerve_update,
            last_wanted_update,
            last_happiness_update,
            last_health_update
        )
        VALUES (
            ?, ?, 150, 20, 150, 20,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        """,
        (user_id, name)
    )

    player_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO player_unlocked_gyms (
            player_id,
            gym_key
        )
        VALUES (?, 'camden_community')
        """,
        (player_id,)
    )

    cursor.executemany(
        """
        INSERT INTO player_inventory (
            player_id,
            item_key,
            quantity
        )
        VALUES (?, ?, 1)
        """,
        (
            (player_id, "first_aid_kit"),
            (player_id, "energy_drink"),
        )
    )

    conn.commit()
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
            residence_key,
            career_key,
            job_role_key,
            career_xp,
            shifts_completed,
            shift_started_at,
            shift_until,
            current_gym_key,
            happiness,
            max_happiness,
            last_happiness_update,
            max_health,
            last_health_update,
            travel_mode
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

    happiness, happiness_update = regenerate_resource(
        current_value=player_data[33],
        maximum_value=player_data[34],
        last_update=player_data[35],
        points_per_tick=HAPPINESS_POINTS_PER_TICK,
        tick_seconds=HAPPINESS_TICK_SECONDS,
        now=now
    )

    hospital_until = player_data[20]
    is_hospitalised = (
        hospital_until is not None
        and parse_timestamp(hospital_until) > now
    )

    if is_hospitalised:
        health, health_update = player_data[5], player_data[37]
    else:
        health, health_update = regenerate_resource(
            current_value=player_data[5],
            maximum_value=player_data[36],
            last_update=player_data[37],
            points_per_tick=HEALTH_POINTS_PER_TICK,
            tick_seconds=HEALTH_TICK_SECONDS,
            now=now
        )

    cursor.execute(
        """
        UPDATE players
        SET
            energy = ?,
            nerve = ?,
            last_energy_update = ?,
            last_nerve_update = ?,
            happiness = ?,
            last_happiness_update = ?,
            health = ?,
            last_health_update = ?
        WHERE id = ?
        """,
        (
            energy,
            nerve,
            energy_update,
            nerve_update,
            happiness,
            happiness_update,
            health,
            health_update,
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

    cursor.execute(
        """
        SELECT gym_key
        FROM player_unlocked_gyms
        WHERE player_id = ?
        """,
        (player_data[0],)
    )
    unlocked_gyms = {
        row[0]
        for row in cursor.fetchall()
    }

    cursor.execute(
        """
        SELECT item_key, quantity
        FROM player_inventory
        WHERE player_id = ?
        """,
        (player_data[0],)
    )
    inventory = dict(cursor.fetchall())

    conn.close()

    player_data[5] = health
    player_data[6] = energy
    player_data[11] = nerve
    player_data[14] = energy_update
    player_data[15] = nerve_update
    player_data[33] = happiness
    player_data[35] = happiness_update
    player_data[37] = health_update

    player_data.extend([
        crime_progress,
        district_reputation,
        unlocked_gyms,
        inventory,
    ])

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
            travel_mode = ?,
            residence_key = ?,
            career_key = ?,
            job_role_key = ?,
            career_xp = ?,
            shifts_completed = ?,
            shift_started_at = ?,
            shift_until = ?,
            current_gym_key = ?,
            happiness = ?,
            max_happiness = ?,
            last_happiness_update = ?,
            max_health = ?,
            last_health_update = ?
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
            player.travel_mode,
            player.residence_key,
            player.career_key,
            player.job_role_key,
            player.career_xp,
            player.shifts_completed,
            player.shift_started_at,
            player.shift_until,
            player.current_gym_key,
            player.happiness,
            player.max_happiness,
            player.last_happiness_update,
            player.max_health,
            player.last_health_update,
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
        "DELETE FROM player_inventory WHERE player_id = ?",
        (player.id,)
    )
    cursor.executemany(
        """
        INSERT INTO player_inventory (
            player_id,
            item_key,
            quantity
        )
        VALUES (?, ?, ?)
        """,
        [
            (player.id, item_key, quantity)
            for item_key, quantity
            in player.inventory.items()
        ]
    )

    cursor.execute(
        "DELETE FROM player_unlocked_gyms WHERE player_id = ?",
        (player.id,)
    )
    cursor.executemany(
        """
        INSERT INTO player_unlocked_gyms (
            player_id,
            gym_key
        )
        VALUES (?, ?)
        """,
        [
            (player.id, gym_key)
            for gym_key in player.unlocked_gyms
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
