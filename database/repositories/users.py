from database.core.connection import get_connection


def create_user(username, email, password_hash):
    username = username.strip()
    email = email.strip().lower()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO users (username, email, password_hash)
        VALUES (?, ?, ?)
        """,
        (username, email, password_hash)
    )

    conn.commit()

    user_id = cursor.lastrowid

    conn.close()

    return user_id


def get_user_by_username(username):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, username, email, password_hash, created_at
        FROM users
        WHERE username = ? COLLATE NOCASE
        """,
        (username.strip(),)
    )

    user = cursor.fetchone()

    conn.close()

    return user


def get_user_by_email(email):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, username, email, password_hash, created_at
        FROM users
        WHERE email = ? COLLATE NOCASE
        """,
        (email.strip().lower(),)
    )

    user = cursor.fetchone()

    conn.close()

    return user


def get_user_by_id(user_id):
    conn = get_connection()

    try:
        return conn.execute(
            """
            SELECT
                id,
                username,
                email,
                password_hash,
                created_at,
                email_verified,
                email_verified_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


def is_email_verified(user_id):
    user = get_user_by_id(user_id)
    return bool(user and user[5])
