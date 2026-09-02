"""Things an attacker would try first.

Written after an audit of the live site. Each of these failed at the
time it was written, which is the only reason it is here -- a security
test that never could have failed is decoration.

Note this directory has no `__init__.py`, so `unittest discover` walks
straight past it. Run it by name.
"""

import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from utils.security import hash_password


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp_dir.name) / "hardening.db",
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        from database.repositories.players import create_player
        from database.repositories.users import create_user

        self.user_id = create_user(
            "realuser", "real@example.com", hash_password("hunter2")
        )
        create_player(self.user_id, "Real")

        from web.application import app

        self.app = app
        self.client = app.test_client()

    def text(self, response):
        body = response.get_data(as_text=True)
        return re.sub(
            r"\s+", " ", re.sub(r"<[^>]+>", " ", body)
        ).strip()

    def sign_in(self, username, password="wrong"):
        return self.client.post(
            "/login", data={"username": username, "password": password}
        )

    # ------------------------------------------- account enumeration

    def test_a_wrong_password_looks_like_a_missing_account(self):
        """The login page used to say which of the two it was.

        That hands over a list of real usernames to anybody willing to
        POST a wordlist at it.
        """
        self.app.config["TESTING"] = True

        self.assertEqual(
            self.text(self.sign_in("realuser")),
            self.text(self.sign_in("nobody-at-all")),
        )

    def test_a_missing_account_costs_the_same_time_as_a_real_one(self):
        """Unifying the message is not enough on its own.

        Returning before bcrypt answers in about a millisecond where a
        real account takes nearly three hundred, which is the same leak
        measured with a stopwatch instead of read off the page.
        """
        self.app.config["TESTING"] = True

        def average(username):
            start = time.perf_counter()
            for _ in range(4):
                self.sign_in(username)
            return (time.perf_counter() - start) / 4

        known = average("realuser")
        missing = average("nobody-at-all")
        ratio = max(known, missing) / max(1e-6, min(known, missing))

        self.assertLess(
            ratio,
            3.0,
            f"a missing account answers {ratio:.0f}x faster than a "
            f"real one, which is enough to enumerate accounts",
        )

    # ------------------------------------------------- brute forcing

    def test_staff_sign_in_is_rate_limited(self):
        """It was the only login in the building without a limit.

        The most valuable password on the site was the easiest one to
        grind.
        """
        self.app.config["TESTING"] = False
        self.addCleanup(
            self.app.config.__setitem__, "TESTING", True
        )

        with patch.dict(os.environ, {
            "THE_SMOKE_ADMIN_USERNAME": "admin",
            "THE_SMOKE_ADMIN_PASSWORD_HASH": hash_password("secret"),
        }):
            codes = [
                self.client.post(
                    "/admin/login",
                    data={"username": "admin", "password": f"guess-{n}"},
                ).status_code
                for n in range(15)
            ]

        self.assertIn(
            429, codes, "staff sign-in accepted fifteen wrong passwords"
        )

    def test_player_sign_in_is_rate_limited(self):
        self.app.config["TESTING"] = False
        self.addCleanup(
            self.app.config.__setitem__, "TESTING", True
        )

        codes = [
            self.sign_in("realuser").status_code for n in range(20)
        ]

        self.assertIn(429, codes)

    # ---------------------------------------------------- headers

    def test_every_response_carries_the_security_headers(self):
        self.app.config["TESTING"] = True

        response = self.client.get("/login")

        for header in (
            "Content-Security-Policy",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Permissions-Policy",
        ):
            with self.subTest(header=header):
                self.assertIn(header, response.headers)

    def test_the_site_cannot_be_framed(self):
        # Clickjacking a game with a "sell everything" button is worth
        # somebody's afternoon.
        self.app.config["TESTING"] = True

        response = self.client.get("/login")

        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn(
            "frame-ancestors 'none'",
            response.headers["Content-Security-Policy"],
        )

    def test_the_policy_does_not_allow_arbitrary_script_sources(self):
        self.app.config["TESTING"] = True

        policy = self.client.get("/login").headers[
            "Content-Security-Policy"
        ]

        self.assertIn("default-src 'self'", policy)
        self.assertIn("base-uri 'none'", policy)
        self.assertNotIn("script-src *", policy)

    # ----------------------------------------------- the session key

    def test_production_refuses_to_start_without_a_session_key(self):
        """A per-worker random key is a silent outage, not a default.

        Each worker would sign cookies differently, so a player would
        be logged in or out depending on which one answered.
        """
        from web.application import _session_secret

        with patch.dict(
            os.environ,
            {"THE_SMOKE_ENVIRONMENT": "production"},
            clear=False,
        ):
            os.environ.pop("THE_SMOKE_SECRET_KEY", None)
            with self.assertRaises(RuntimeError):
                _session_secret()

    def test_development_still_gets_a_working_key(self):
        from web.application import _session_secret

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("THE_SMOKE_SECRET_KEY", None)
            os.environ.pop("THE_SMOKE_ENVIRONMENT", None)
            self.assertTrue(_session_secret())


if __name__ == "__main__":
    unittest.main()
