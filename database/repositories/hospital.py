from database.core.connection import get_connection


def get_hospital_patients(limit=50):
    """Return players whose hospital stay has not expired."""
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                name,
                level,
                health,
                hospital_until,
                MAX(
                    0,
                    CAST(
                        (JULIANDAY(hospital_until)
                        - JULIANDAY(CURRENT_TIMESTAMP))
                        * 86400 AS INTEGER
                    )
                ) AS remaining_seconds
            FROM players
            WHERE
                hospital_until IS NOT NULL
                AND hospital_until > CURRENT_TIMESTAMP
            ORDER BY hospital_until ASC, name ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "name": row[0],
                "level": row[1],
                "health": row[2],
                "hospital_until": row[3],
                "remaining_seconds": row[4],
                "reason": "Recovering from injuries",
            }
            for row in rows
        ]
    finally:
        connection.close()
