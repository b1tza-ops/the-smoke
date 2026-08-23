from database.repositories.users import create_user, get_user_by_username, get_user_by_email
from utils.security import hash_password


def register():
    print("\n===== REGISTER =====")

    username = input("Username: ").strip()
    email = input("Email: ").strip().lower()
    password = input("Password: ")

    if get_user_by_username(username):
        print("Username already taken.")
        return

    if get_user_by_email(email):
        print("Email already registered.")
        return

    if len(password) < 6:
        print("Password must be at least 6 characters.")
        return

    password_hash = hash_password(password)

    user_id = create_user(
        username,
        email,
        password_hash
    )

    print("\nAccount created successfully!")
    print("User ID:", user_id)