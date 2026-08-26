import hashlib
import hmac

import bcrypt


BCRYPT_MAX_PASSWORD_BYTES = 72


def _bcrypt_bytes(password):
    """Encode a password the way bcrypt can actually consume it.

    bcrypt only ever reads the first 72 bytes of a password. Older
    releases dropped the rest silently; from 4.0 onwards the library
    raises ValueError instead, which escaped every call site here and
    turned a long password into a 500 on register, sign-in and password
    reset alike.

    Clamping here keeps both versions behaving identically, so hashes
    written under the older library still verify. Note the slice is on
    bytes, not characters: a password of 27 emoji is over the limit even
    though it looks short, and cutting mid-sequence is fine because
    bcrypt hashes bytes and never decodes them.
    """
    return password.encode("utf-8")[:BCRYPT_MAX_PASSWORD_BYTES]


def hash_password(password):
    hashed = bcrypt.hashpw(
        _bcrypt_bytes(password),
        bcrypt.gensalt()
    )

    return hashed.decode("utf-8")


def verify_password(password, password_hash):
    return bcrypt.checkpw(
        _bcrypt_bytes(password),
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
