from auth.validation import (
    ValidationError,
    normalize_email,
    validate_password,
    validate_username,
)
from database.repositories.users import (
    create_user,
    get_user_by_email,
    get_user_by_username,
)
from utils.security import hash_password


def register():
    print("\n===== REGISTER =====")

    try:
        username = validate_username(
            input("Username: ")
        )
        email = normalize_email(
            input("Email: ")
        )
        password = validate_password(
            input("Password: ")
        )
    except ValidationError as error:
        print(str(error))
        return None

    if get_user_by_username(username):
        print("Username already taken.")
        return None

    if get_user_by_email(email):
        print("Email already registered.")
        return None

    password_hash = hash_password(password)

    user_id = create_user(
        username,
        email,
        password_hash
    )

    print("\nAccount created successfully!")
    print("User ID:", user_id)
    return user_id
