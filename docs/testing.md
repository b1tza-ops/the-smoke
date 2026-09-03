# Testing The Smoke

Run the complete automated suite from the repository root:

    python3 -m unittest discover -s tests -v

That is the whole suite. No directory in `tests/` may be named after a
top-level package — `tests/auth/` once was, and because discovery puts
`tests/` on the front of the path it replaced the real `auth/` package for the
entire run. The authentication tests live in `tests/authentication/`, and
`tests/test_suite_integrity.py` fails if the collision is ever reintroduced.

The same command runs for every push and pull request in GitHub Actions.
Tests that touch SQLite patch the configured database path and use temporary
directories, so the local data/game.db file is never modified.

## V1 coverage map

| Area | Main coverage |
| --- | --- |
| Authentication | bcrypt hashes, hashed one-time tokens, generic recovery responses, expiry, reuse, validation, rate limiting |
| Player persistence | XP, crime progress, status, bank, travel, housing, jobs, gyms, and inventory save/reload |
| Regeneration | completed ticks, exact tick boundaries, cap enforcement, repeated loading |
| Crimes | zero/exact nerve, rewards, XP, reputation, consequences, travel and district restrictions |
| Progression | XP thresholds, multi-level rewards, invalid negative values |
| Resources | zero/exact energy, zero/exact nerve, maximum caps |

## Test-data rule

Any new database test must use tempfile.TemporaryDirectory and patch
database.core.connection.DB_PATH. Never point an automated test at the real
game database.

## Before opening a pull request

Run:

    python3 -m unittest discover -s tests -v
    python3 -m compileall -q app.py main.py auth cli database game tests web
    git diff --check
