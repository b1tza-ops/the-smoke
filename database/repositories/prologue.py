from database.core.connection import get_connection


BACKGROUNDS = {
    "street_hustler": {
        "name": "Street Hustler",
        "description": "You know when to talk, when to run and who not to trust.",
        "bonus": "+5 maximum nerve",
    },
    "former_athlete": {
        "name": "Former Athlete",
        "description": "Discipline survived even after everything else fell apart.",
        "bonus": "+10 maximum energy",
    },
    "local_worker": {
        "name": "Local Worker",
        "description": "You understand long shifts, thin margins and real money.",
        "bonus": "+£250 starting cash",
    },
}

OPENING_CHOICES = {
    "talk_your_way_in": {
        "name": "Talk your way in",
        "style": "Persuasion",
        "description": "Pose as a courier, read the room and get the ledger without a scene.",
        "stat": "dexterity",
        "required_stat": 8,
        "energy": 5,
        "nerve": 3,
        "duration_seconds": 60,
        "paydown": 300,
        "cash": 80,
        "xp": 30,
        "wanted": 0,
        "risk": "Low",
        "outcome": "The receptionist remembered your smile, not your name. The ledger is yours and nobody raised the alarm.",
    },
    "slip_through_back": {
        "name": "Slip through the back",
        "style": "Stealth",
        "description": "Use the service alley, avoid the cameras and lift the ledger quietly.",
        "stat": "speed",
        "required_stat": 10,
        "energy": 8,
        "nerve": 5,
        "duration_seconds": 90,
        "paydown": 425,
        "cash": 120,
        "xp": 40,
        "wanted": 1,
        "risk": "Medium",
        "outcome": "A camera caught only a hood and a blur. You escaped with the ledger before anyone checked the office.",
    },
    "force_the_door": {
        "name": "Force the door",
        "style": "Force",
        "description": "Move fast, break the lock and accept that Camden will hear about it.",
        "stat": "strength",
        "required_stat": 10,
        "energy": 12,
        "nerve": 7,
        "duration_seconds": 120,
        "paydown": 550,
        "cash": 180,
        "xp": 55,
        "wanted": 5,
        "risk": "High",
        "outcome": "The door gave way and so did the guard. You have the ledger, but sirens carried your name across Camden.",
    },
}

# Existing completed accounts may contain these V1 choice keys.
LEGACY_CHOICES = {
    "deliver_package": {
        "name": "Deliver the package",
        "style": "Courier",
        "description": "No questions. King's Cross. Before midnight.",
        "paydown": 350,
        "cash": 0,
        "xp": 25,
        "wanted": 2,
        "outcome": "The package was warm. Your contact paid without counting—and now knows you can be useful.",
    },
    "steal_watch": {
        "name": "Steal the watch",
        "style": "Theft",
        "description": "A mark left a Camden bar. Quick money, serious risk.",
        "paydown": 500,
        "cash": 0,
        "xp": 40,
        "wanted": 5,
        "outcome": "The watch is gone and someone saw your face. You earned respect, money and attention.",
    },
    "refuse_offer": {
        "name": "Refuse and work",
        "style": "Legal",
        "description": "You walked away and unloaded a night van for honest cash.",
        "paydown": 200,
        "cash": 0,
        "xp": 15,
        "wanted": 0,
        "outcome": "You kept your hands clean. The unknown number texted once more: 'Everyone changes their mind.'",
    },
}
ALL_OPENING_CHOICES = {**OPENING_CHOICES, **LEGACY_CHOICES}


def get_or_create_prologue(user_id):
    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO player_prologue (user_id)
            VALUES (?)
            """,
            (user_id,),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT
                background,
                opening_choice,
                debt_remaining,
                debt_due_at,
                outcome_text,
                completed_at,
                operation_stage,
                operation_started_at,
                operation_ready_at,
                operation_approach,
                CASE
                    WHEN operation_ready_at IS NULL THEN 0
                    ELSE MAX(
                        0,
                        CAST(
                            (JULIANDAY(operation_ready_at)
                            - JULIANDAY(CURRENT_TIMESTAMP))
                            * 86400 AS INTEGER
                        )
                    )
                END
            FROM player_prologue
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return {
            "background": row[0],
            "opening_choice": row[1],
            "debt_remaining": row[2],
            "debt_due_at": row[3],
            "outcome_text": row[4],
            "completed_at": row[5],
            "operation_stage": row[6],
            "operation_started_at": row[7],
            "operation_ready_at": row[8],
            "operation_approach": row[9] or row[1],
            "remaining_seconds": row[10],
        }
    finally:
        connection.close()


def choose_background(user_id, background):
    if background not in BACKGROUNDS:
        raise ValueError("Choose one of the available backgrounds.")

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute(
            "SELECT background FROM player_prologue WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if current is None:
            raise ValueError("Your dossier could not be found.")
        if current[0] is not None:
            raise ValueError("Your background has already been chosen.")

        cursor = connection.execute(
            """
            UPDATE player_prologue
            SET background = ?, operation_stage = 'briefing'
            WHERE user_id = ? AND background IS NULL
            """,
            (background, user_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Your background has already been chosen.")

        if background == "street_hustler":
            connection.execute(
                """
                UPDATE players
                SET max_nerve = max_nerve + 5,
                    nerve = nerve + 5
                WHERE user_id = ?
                """,
                (user_id,),
            )
        elif background == "former_athlete":
            connection.execute(
                """
                UPDATE players
                SET max_energy = max_energy + 10,
                    energy = energy + 10
                WHERE user_id = ?
                """,
                (user_id,),
            )
        else:
            connection.execute(
                "UPDATE players SET money = money + 250 WHERE user_id = ?",
                (user_id,),
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def start_opening_operation(user_id, choice):
    operation = OPENING_CHOICES.get(choice)
    if operation is None:
        raise ValueError("Choose one of the available approaches.")

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = connection.execute(
            """
            SELECT
                story.background,
                story.completed_at,
                story.operation_stage,
                player.energy,
                player.nerve,
                player.strength,
                player.speed,
                player.dexterity,
                player.jail_until,
                player.hospital_until,
                player.travel_destination
            FROM player_prologue AS story
            JOIN players AS player ON player.user_id = story.user_id
            WHERE story.user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if state is None or state[0] is None:
            raise ValueError("Complete your dossier first.")
        if state[1] is not None or state[2] == "completed":
            raise ValueError("This operation is already complete.")
        if state[2] == "active":
            raise ValueError("You already have an active operation.")
        if state[8] is not None:
            raise ValueError("You cannot begin an operation from jail.")
        if state[9] is not None:
            raise ValueError("You cannot begin an operation from hospital.")
        if state[10] is not None:
            raise ValueError("You cannot begin an operation while travelling.")

        stats = {
            "strength": state[5],
            "speed": state[6],
            "dexterity": state[7],
        }
        if stats[operation["stat"]] < operation["required_stat"]:
            raise ValueError(
                f"You need {operation['required_stat']} "
                f"{operation['stat']} for this approach."
            )
        if state[3] < operation["energy"]:
            raise ValueError("You do not have enough energy.")
        if state[4] < operation["nerve"]:
            raise ValueError("You do not have enough nerve.")

        duration = f"+{operation['duration_seconds']} seconds"
        connection.execute(
            """
            UPDATE players
            SET energy = energy - ?, nerve = nerve - ?
            WHERE user_id = ?
            """,
            (operation["energy"], operation["nerve"], user_id),
        )
        connection.execute(
            """
            UPDATE player_prologue
            SET
                operation_approach = ?,
                operation_stage = 'active',
                operation_started_at = CURRENT_TIMESTAMP,
                operation_ready_at = DATETIME(CURRENT_TIMESTAMP, ?)
            WHERE user_id = ?
            """,
            (choice, duration, user_id),
        )
        connection.commit()
        return operation
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def resolve_opening_operation(user_id):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = connection.execute(
            """
            SELECT operation_approach, operation_stage, operation_ready_at
            FROM player_prologue
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if state is None or state[1] != "active":
            raise ValueError("There is no active operation to resolve.")
        if state[2] > connection.execute(
            "SELECT CURRENT_TIMESTAMP"
        ).fetchone()[0]:
            raise ValueError("The operation is still in progress.")

        operation = OPENING_CHOICES.get(state[0])
        if operation is None:
            raise ValueError("The active operation could not be found.")

        connection.execute(
            """
            UPDATE player_prologue
            SET
                debt_remaining = MAX(0, debt_remaining - ?),
                outcome_text = ?,
                completed_at = CURRENT_TIMESTAMP,
                operation_stage = 'completed'
            WHERE user_id = ? AND completed_at IS NULL
            """,
            (operation["paydown"], operation["outcome"], user_id),
        )
        connection.execute(
            """
            UPDATE players
            SET
                money = money + ?,
                xp = xp + ?,
                wanted_level = MIN(100, wanted_level + ?)
            WHERE user_id = ?
            """,
            (
                operation["cash"],
                operation["xp"],
                operation["wanted"],
                user_id,
            ),
        )
        connection.commit()
        return operation
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def complete_opening_mission(user_id, choice):
    """Compatibility path for the original immediate prologue API."""
    mission = LEGACY_CHOICES.get(choice)
    if mission is None:
        raise ValueError("Choose one of the available paths.")

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = connection.execute(
            """
            SELECT background, completed_at
            FROM player_prologue
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if state is None or state[0] is None:
            raise ValueError("Choose your background first.")
        if state[1] is not None:
            raise ValueError("The opening mission is already complete.")

        cursor = connection.execute(
            """
            UPDATE player_prologue
            SET
                opening_choice = ?,
                debt_remaining = MAX(0, debt_remaining - ?),
                outcome_text = ?,
                completed_at = CURRENT_TIMESTAMP,
                operation_stage = 'completed'
            WHERE user_id = ? AND completed_at IS NULL
            """,
            (choice, mission["paydown"], mission["outcome"], user_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("The opening mission is already complete.")

        connection.execute(
            """
            UPDATE players
            SET xp = xp + ?,
                wanted_level = MIN(100, wanted_level + ?)
            WHERE user_id = ?
            """,
            (mission["xp"], mission["wanted"], user_id),
        )
        connection.commit()
        return mission
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
