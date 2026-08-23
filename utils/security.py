import hashlib
import hmac

import bcrypt


def hash_password(password):
    password_bytes = password.encode("utf-8")

    hashed = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt()
    )

    return hashed.decode("utf-8")


def verify_password(password, password_hash):
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )


def hash_token(raw_token):
    if not isinstance(raw_token, str):
        raise TypeError("Token must be text.")

    return hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()


def token_hash_matches(raw_token, token_hash):
    return hmac.compare_digest(
        hash_token(raw_token),
        token_hash,
    )
