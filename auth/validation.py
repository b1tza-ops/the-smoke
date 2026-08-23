import re


MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,30}$")
EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


class ValidationError(ValueError):
    """Raised when account input is invalid."""


def validate_username(username):
    if not isinstance(username, str):
        raise ValidationError(
            "Username must be text."
        )

    username = username.strip()

    if not USERNAME_PATTERN.fullmatch(username):
        raise ValidationError(
            "Username must be 3-30 characters and use "
            "only letters, numbers, or underscores."
        )

    return username


def normalize_email(email):
    if not isinstance(email, str):
        raise ValidationError(
            "Email address must be text."
        )

    email = email.strip().lower()

    if (
        len(email) > 254
        or not EMAIL_PATTERN.fullmatch(email)
    ):
        raise ValidationError(
            "Enter a valid email address."
        )

    return email


def validate_password(password):
    if not isinstance(password, str):
        raise ValidationError(
            "Password must be text."
        )

    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            "Password must be at least "
            f"{MIN_PASSWORD_LENGTH} characters."
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(
            "Password is too long."
        )

    return password
