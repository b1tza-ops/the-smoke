from database.core.connection import get_connection


def get_jail_inmates(limit=50):
    """Return players whose jail sentence has not expired."""
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                id,
                name,
                level,
                wanted_level,
                jail_until,
                MAX(
                    0,
                    CAST(
                        (JULIANDAY(jail_until)
                        - JULIANDAY(CURRENT_TIMESTAMP))
                        * 86400 AS INTEGER
                    )
                ) AS remaining_seconds
            FROM players
            WHERE
                jail_until IS NOT NULL
                AND jail_until > CURRENT_TIMESTAMP
            ORDER BY jail_until ASC, name ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "level": row[2],
                "wanted_level": row[3],
                "jail_until": row[4],
                "remaining_seconds": row[5],
                "reason": "Arrested after a failed crime",
            }
            for row in rows
        ]
    finally:
        connection.close()
