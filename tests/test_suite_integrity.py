"""Does the suite actually run the tests it appears to contain?

Twice now this project has shipped tests that read as coverage and
executed nothing. `tests/auth/` has no `__init__.py`, so discovery walks
straight past all five files in it. And four files were written in the
pytest style -- bare `def test_...` functions with plain `assert` -- which
`unittest` does not collect at all, so seventeen tests sat green by
never running. One of them was guarding combat payouts while the payout
rule was rewritten underneath it.

A test that cannot fail is worse than no test, because it reads as
cover. These two hold the suite honest about its own size.
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


class SuiteIntegrityTests(unittest.TestCase):
    def test_every_test_file_contributes_at_least_one_test(self):
        """No file may sit in tests/ contributing nothing.

        Loaded individually, so a directory missing its `__init__.py`
        is still checked -- that is the other way tests go quiet here.
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

    def test_no_test_is_written_as_a_bare_function(self):
        """The style that caused it, caught at the file level.

        `unittest` only collects methods on a `TestCase`. A module-level
        `def test_...` is never called, and nothing complains.
        """
        offenders = []

        for path in test_files():
            if path.name == Path(__file__).name:
                continue

            bare = [
                line.split("(")[0].removeprefix("def ").strip()
                for line in path.read_text().splitlines()
                if line.startswith("def test_")
            ]
            if bare:
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)}: {', '.join(bare)}"
                )

        self.assertEqual(
            offenders,
            [],
            "module-level test functions are never run by unittest; "
            "move them onto a TestCase -- " + " | ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
