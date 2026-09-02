# Testing The Smoke

Run the complete automated suite from the repository root:

    python3 -m unittest discover -s tests -t . -v

The `-t .` is load-bearing: it roots discovery at the project so that
`tests/auth/` is a package rather than something that shadows the real `auth/`
package. Drop it and thirty-six authentication tests are skipped without a
word. `tests/test_suite_integrity.py` fails if that ever happens again.

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

    python3 -m unittest discover -s tests -t . -v
    python3 -m compileall -q app.py main.py auth cli database game tests web
    git diff --check
