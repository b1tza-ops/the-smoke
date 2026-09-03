"""Does the suite actually run the tests it appears to contain?

Three times now this project has shipped tests that read as coverage and
executed nothing.

`tests/auth/` had no `__init__.py`, so discovery walked straight past
all six files in it -- every check on password hashing, login timing,
the admin rate limit and Turnstile, passing on demand and never once on
a push. Adding the `__init__.py` was worse: `tests/auth` then shadowed
the real `auth` package, and seventy-seven unrelated tests died on the
import instead. The directory is now `tests/authentication/`, which
collides with nothing, and `test_no_test_directory_shadows_a_real_one`
below is what stops the next one being reintroduced.

And four files were written in the pytest style -- bare `def test_...`
functions with plain `assert` -- which `unittest` does not collect at
all, so seventeen tests sat green by never running. One of them was
guarding combat payouts while the payout rule was rewritten underneath
it.

A test that cannot fail is worse than no test, because it reads as
cover. These hold the suite honest about its own size.
"""

import unittest
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_ROOT.parent


def test_files():
    return sorted(TESTS_ROOT.rglob("test_*.py"))


def module_name(path):
    relative = path.relative_to(PROJECT_ROOT).with_suffix("")
    return ".".join(relative.parts)


def discovered_name(path):
    """The dotted name discovery gives a file under `-s tests`.

    Rooted at `tests/` rather than at the project, because that is the
    command CI and the deploy script actually run. Pinning the other
    rooting would let this pass while the real invocation broke.
    """
    relative = path.relative_to(TESTS_ROOT).with_suffix("")
    return ".".join(relative.parts)


def _flatten(suite):
    """Every TestCase in a suite, however deeply nested.

    A failed import becomes a `_FailedTest` whose module is the loader
    rather than the file, so it never counts as reached -- which is the
    behaviour wanted: a file that cannot be imported has not been
    discovered in any useful sense.
    """
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


class SuiteIntegrityTests(unittest.TestCase):
    def test_every_test_file_contributes_at_least_one_test(self):
        """No file may sit in tests/ contributing nothing.

        Loaded individually, so a directory missing its `__init__.py`
        is still checked -- that is one of the ways tests go quiet
        here.
        """
        loader = unittest.TestLoader()
        empty = []

        for path in test_files():
            if path.name == Path(__file__).name:
                continue

            suite = loader.loadTestsFromName(module_name(path))
            if suite.countTestCases() == 0:
                empty.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(
            empty,
            [],
            "these files run no tests at all: " + ", ".join(empty),
        )

    def test_no_test_directory_shadows_a_real_one(self):
        """The cause, rather than the symptom.

        `discover -s tests` puts `tests/` on the front of the path, so
        a package in here named after a real one takes its place for
        the whole run. `tests/auth/` did exactly that, and the failure
        it produced -- `No module named 'auth.email_delivery'`, seventy
        -seven files deep -- points nowhere near the directory that
        caused it.

        Checked against the source tree rather than a written-down
        list, so a package added at the top level tomorrow is covered
        without anybody remembering this test exists.

        Both sides need their `__init__.py` for this to bite, and the
        first draft of this test only checked the name. A directory
        with no `__init__.py` is a *namespace* package, and a namespace
        package loses to a regular one further down the path -- so a
        bare `tests/auth/` left behind by the rename, holding nothing
        but a stale `__pycache__`, shadows precisely nothing. Flagging
        it sent somebody looking for a fault that was not there, which
        is the same sin as missing a real one.
        """
        packages = {
            entry.name
            for entry in PROJECT_ROOT.iterdir()
            if entry.is_dir()
            and (entry / "__init__.py").exists()
            and entry != TESTS_ROOT
        }
        shadows = sorted(
            entry.name
            for entry in TESTS_ROOT.iterdir()
            if entry.is_dir()
            and entry.name in packages
            and (entry / "__init__.py").exists()
        )

        self.assertEqual(
            shadows,
            [],
            "these directories shadow a real package for the whole "
            "run: " + ", ".join(shadows),
        )

    def test_discovery_reaches_every_file_the_suite_contains(self):
        """The other half: found individually is not found by CI.

        The guard above loads each file by name, so it stays honest
        about a directory discovery cannot see. This one runs the
        command CI runs and checks that every file turns up in it.
        """
        discovered = {
            type(case).__module__
            for case in _flatten(
                unittest.TestLoader().discover(str(TESTS_ROOT))
            )
        }
        missed = sorted(
            discovered_name(path)
            for path in test_files()
            if discovered_name(path) not in discovered
        )

        self.assertEqual(
            missed,
            [],
            "discovery never reaches these files: " + ", ".join(missed),
        )

    def test_no_test_is_written_as_a_bare_function(self):
        """The style that caused it, caught at the file level.

        `unittest` only collects methods on a `TestCase`. A module-level
        `def test_...` is never called, and nothing complains.
        """
        offenders = []

        for path in test_files():
            if path.name == Path(__file__).name:
                continue

            for number, line in enumerate(
                path.read_text().splitlines(), start=1
            ):
                if line.startswith("def test_"):
                    offenders.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{number}"
                    )

        self.assertEqual(
            offenders,
            [],
            "module-level test functions never run under unittest: "
            + ", ".join(offenders),
        )
