from contextlib import closing
from datetime import datetime, timedelta, timezone
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from auth.rate_limit import (
    InMemoryRateLimiter,
    RateLimitExceededError,
    enforce_rate_limit,
)
from auth.services.password_reset import (
    ExpiredAccountTokenError,
    InvalidAccountTokenError,
    GENERIC_RESET_MESSAGE,
    UsedAccountTokenError,
    request_email_verification,
    request_password_reset,
    reset_password,
    verify_email_token,
)
from auth.validation import (
    ValidationError,
    normalize_email,
    validate_password,
    validate_username,
)
from database.core.setup import create_tables
from database.repositories.users import (
    create_user,
    get_user_by_email,
)
from utils.security import (
    hash_password,
    hash_token,
    verify_password,
)


class AuthenticationSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_dir.name) / "game.db"
        )
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            self.database_path,
        )
        self.database_patch.start()
        create_tables()

        self.user_id = create_user(
            "SecurePlayer",
            "secure@example.com",
            hash_password("old-password"),
        )
        self.now = datetime(
            2026,
            8,
            23,
            20,
            0,
            tzinfo=timezone.utc,
        )

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_password_hash_does_not_store_raw_password(self):
        user = get_user_by_email(
            "secure@example.com"
        )

        self.assertNotEqual(
            user[3],
            "old-password",
        )
        self.assertTrue(
            verify_password(
                "old-password",
                user[3],
            )
        )

    def test_reset_request_is_generic_for_known_and_unknown_email(self):
        deliveries = []

        known_result = request_password_reset(
            "SECURE@example.com",
            delivery=lambda *values: deliveries.append(values),
            now=self.now,
            token_factory=lambda: "known-raw-token",
        )
        unknown_result = request_password_reset(
            "missing@example.com",
            delivery=lambda *values: deliveries.append(values),
            now=self.now,
        )

        self.assertEqual(
            known_result.message,
            GENERIC_RESET_MESSAGE,
        )
        self.assertEqual(
            unknown_result.message,
            GENERIC_RESET_MESSAGE,
        )
        self.assertEqual(len(deliveries), 1)

    def test_raw_reset_token_is_never_stored(self):
        deliveries = []

        request_password_reset(
            "secure@example.com",
            delivery=lambda *values: deliveries.append(values),
            now=self.now,
            token_factory=lambda: "raw-reset-token",
        )

        raw_token = deliveries[0][1]

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            stored_hash = conn.execute(
                """
                SELECT token_hash
                FROM account_tokens
                """
            ).fetchone()[0]

        self.assertEqual(
            stored_hash,
            hash_token(raw_token),
        )
        self.assertNotEqual(
            stored_hash,
            raw_token,
        )

    def test_password_reset_changes_password_and_rejects_reuse(self):
        deliveries = []
        request_password_reset(
            "secure@example.com",
            delivery=lambda *values: deliveries.append(values),
            now=self.now,
            token_factory=lambda: "single-use-token",
        )
        raw_token = deliveries[0][1]

        self.assertTrue(
            reset_password(
                raw_token,
                "new-password",
                now=self.now + timedelta(minutes=1),
            )
        )

        user = get_user_by_email(
            "secure@example.com"
        )
        self.assertTrue(
            verify_password(
                "new-password",
                user[3],
            )
        )

        with self.assertRaises(
            UsedAccountTokenError
        ):
            reset_password(
                raw_token,
                "another-password",
                now=self.now + timedelta(minutes=2),
            )

    def test_expired_password_reset_token_is_rejected(self):
        deliveries = []
        request_password_reset(
            "secure@example.com",
            delivery=lambda *values: deliveries.append(values),
            now=self.now,
            token_factory=lambda: "expired-token",
        )

        with self.assertRaises(
            ExpiredAccountTokenError
        ):
            reset_password(
                deliveries[0][1],
                "new-password",
                now=self.now + timedelta(minutes=31),
            )

    def test_email_verification_is_single_use(self):
        deliveries = []
        request_email_verification(
            self.user_id,
            "secure@example.com",
            delivery=lambda *values: deliveries.append(values),
            now=self.now,
            token_factory=lambda: "verification-token",
        )
        raw_token = deliveries[0][1]

        self.assertTrue(
            verify_email_token(
                raw_token,
                now=self.now + timedelta(minutes=1),
            )
        )

        with closing(
            sqlite3.connect(self.database_path)
        ) as conn:
            verification = conn.execute(
                """
                SELECT
                    email_verified,
                    email_verified_at
                FROM users
                WHERE id = ?
                """,
                (self.user_id,),
            ).fetchone()

        self.assertEqual(verification[0], 1)
        self.assertIsNotNone(verification[1])

        with self.assertRaises(
            UsedAccountTokenError
        ):
            verify_email_token(
                raw_token,
                now=self.now + timedelta(minutes=2),
            )

    def test_in_memory_rate_limit_hook_blocks_and_recovers(self):
        limiter = InMemoryRateLimiter(
            limit=2,
            window_seconds=60,
        )

        enforce_rate_limit(
            limiter,
            "login:player",
            now=self.now,
        )
        enforce_rate_limit(
            limiter,
            "login:player",
            now=self.now + timedelta(seconds=1),
        )

        with self.assertRaises(
            RateLimitExceededError
        ):
            enforce_rate_limit(
                limiter,
                "login:player",
                now=self.now + timedelta(seconds=2),
            )

        enforce_rate_limit(
            limiter,
            "login:player",
            now=self.now + timedelta(seconds=61),
        )

    def test_invalid_reset_token_does_not_change_password(self):
        with self.assertRaises(
            InvalidAccountTokenError
        ):
            reset_password(
                "not-a-real-token",
                "new-password",
                now=self.now,
            )

        user = get_user_by_email(
            "secure@example.com"
        )
        self.assertTrue(
            verify_password(
                "old-password",
                user[3],
            )
        )

    def test_account_input_validation(self):
        self.assertEqual(
            validate_username(" Player_1 "),
            "Player_1",
        )
        self.assertEqual(
            normalize_email(" USER@Example.COM "),
            "user@example.com",
        )
        self.assertEqual(
            validate_password("password"),
            "password",
        )

        for invalid_username in (
            "ab",
            "bad name",
            "bad!",
        ):
            with self.assertRaises(
                ValidationError
            ):
                validate_username(
                    invalid_username
                )

        for invalid_email in (
            "missing-at",
            "@example.com",
        ):
            with self.assertRaises(
                ValidationError
            ):
                normalize_email(invalid_email)

        with self.assertRaises(
            ValidationError
        ):
            validate_password("short")


if __name__ == "__main__":
    unittest.main()
