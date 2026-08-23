from database.repositories.users import get_user_by_username
from utils.security import verify_password

def login():
    print("\n===== LOGIN =====")

    username = input("Username: ").strip()
    password = input("Password: ")

    user = get_user_by_username(username)

    if user is None:
        print("User not found.")
        return None

    user_id = user[0]
    stored_username = user[1]
    password_hash = user[3]

    if not verify_password(password, password_hash):
        print("Incorrect password.")
        return None

    print("\nLogin successful!")
    print("Welcome back,", stored_username)

    return user_id
