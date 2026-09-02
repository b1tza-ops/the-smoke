"""The two things this project installs, and whether they are what runs.

`requirements.txt` had `bcrypt==3.2.2` pinned while every machine that
mattered was running 5.0.0. Nothing noticed, because nothing compares
them: CI installs the pin and tests the pin, the server installs the pin
and tests the pin, and a developer box that got its bcrypt some other
way tests something else entirely.

That is a bad way to find out. The 3.x line is a cffi build that does
not compile on the Python the server runs, so the first clean install
would not have been a subtly different bcrypt -- it would have been no
bcrypt at all, and nobody able to log in.
"""

import re
import unittest
from importlib import metadata
from pathlib import Path


REQUIREMENTS = Path(__file__).resolve().parents[2] / "requirements.txt"
PIN = re.compile(r"^([A-Za-z0-9_.\-]+)==([0-9][^\s#]*)\s*$")


def pins():
    found = {}
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.match(line)
        if match:
            found[match.group(1).lower()] = match.group(2)
    return found


class RequirementsTests(unittest.TestCase):
    def test_every_dependency_is_pinned_exactly(self):
        """No ranges. A game with live balances does not want surprises."""
        lines = [
            line.strip()
            for line in REQUIREMENTS.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        self.assertEqual(
            [line for line in lines if not PIN.match(line)],
            [],
        )

    def test_the_pins_are_what_is_actually_installed(self):
        """The whole point of the file.

        Green against a library the site does not use is not green. If
        this fails, either the environment drifted or the pin did --
        find out which before shipping anything.
        """
        for name, pinned in pins().items():
            with self.subTest(package=name):
                self.assertEqual(
                    metadata.version(name),
                    pinned,
                    f"{name} is pinned at {pinned} and "
                    f"{metadata.version(name)} is installed",
                )

    def test_bcrypt_and_flask_are_the_whole_list(self):
        """Two dependencies is a feature, not an accident.

        Everything else here is the standard library, which is what
        makes this deployable on a box with nothing on it. A third
        entry should be a decision somebody made on purpose.
        """
        self.assertEqual(sorted(pins()), ["bcrypt", "flask"])


class PasswordHashingTests(unittest.TestCase):
    """That the installed bcrypt still reads hashes written by the old one.

    The pin moved from 3.2.2 to 5.0.0, which is a major version across
    a rewrite from cffi to Rust. Stored hashes are the one thing that
    cannot be regenerated: get this wrong and every existing player is
    locked out permanently.
    """

    def test_a_stored_cost_twelve_hash_still_verifies(self):
        """A fixed hash, checked rather than regenerated.

        Regenerating it each run would only prove the library agrees
        with itself. What matters is that a string sitting in the
        players table since before the upgrade still opens, so the
        string is written down here and never touched again.
        """
        from utils.security import verify_password

        stored = (
            "$2b$12$Res90uszB.DErb3.LEzzU.9fScEElT/dk3xTbd5stPDpHkZYOVBGW"
        )

        self.assertTrue(verify_password("secret", stored))
        self.assertFalse(verify_password("Secret", stored))

    def test_the_hashes_it_writes_are_the_same_shape(self):
        from utils.security import hash_password, verify_password

        written = hash_password("correct horse battery staple")

        self.assertTrue(written.startswith("$2b$"))
        self.assertEqual(len(written), 60)
        self.assertTrue(
            verify_password("correct horse battery staple", written)
        )


if __name__ == "__main__":
    unittest.main()
