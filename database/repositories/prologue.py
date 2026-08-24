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
    "deliver_package": {
        "name": "Deliver the package",
        "description": "No questions. King’s Cross. Before midnight.",
        "paydown": 350,
        "xp": 25,
        "wanted": 2,
        "outcome": "The package was warm. Your contact paid without counting—and now knows you can be useful.",
    },
    "steal_watch": {
        "name": "Steal the watch",
        "description": "A mark is leaving a Camden bar. Quick money, serious risk.",
        "paydown": 500,
        "xp": 40,
        "wanted": 5,
        "outcome": "The watch is gone and someone saw your face. You earned respect, money and attention.",
    },
    "refuse_offer": {
        "name": "Refuse and work",
        "description": "Walk away and unload a night van for honest cash.",
        "paydown": 200,
        "xp": 15,
        "wanted": 0,
        "outcome": "You kept your hands clean tonight. The unknown number texted once more: ‘Everyone changes their mind.’",
    },
}


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
                completed_at
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
            raise ValueError("Opening story could not be found.")

        if current[0] is not None:
            raise ValueError("Your background has already been chosen.")

        cursor = connection.execute(
            """
            UPDATE player_prologue
            SET background = ?
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


def complete_opening_mission(user_id, choice):
    mission = OPENING_CHOICES.get(choice)

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
                completed_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND completed_at IS NULL
            """,
            (choice, mission["paydown"], mission["outcome"], user_id),
        )

        if cursor.rowcount != 1:
            raise ValueError("The opening mission is already complete.")

        connection.execute(
            """
            UPDATE players
            SET
                xp = xp + ?,
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
