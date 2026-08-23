# Database migrations

The Smoke currently uses SQLite.

A database migration upgrades an existing `game.db` schema to a newer version without deleting player data or requiring manual SQL commands.

## Current schema versions

| Version | Name | Purpose |
|---|---|---|
| 1 | `player_progression_and_resources` | Adds XP, nerve limits and regeneration timestamps |
| 2 | `player_status` | Adds wanted level, jail and hospital status |
| 3 | `bank_system` | Adds protected bank balances and the transaction ledger |

Applied versions are stored in the `schema_migrations` table.

## Startup flow

When `create_tables()` runs:

1. Missing core tables are created.
2. `run_migrations()` reads `schema_migrations`.
3. Pending migrations run in version order.
4. Each successful version is recorded.
5. Already-applied versions are skipped.
6. A failed migration is rolled back.

## Adding a migration

Every schema change must receive the next sequential version.

For example, travel could become version 4:

```python
def migrate_004_travel(cursor):
    add_missing_player_columns(
        cursor,
        {
            "current_district": (
                "TEXT NOT NULL DEFAULT 'Camden'"
            ),
            "travel_destination": "TEXT",
            "travel_until": "TEXT",
        },
    )
```

Register it in `MIGRATIONS`:

```python
Migration(
    version=4,
    name="travel",
    apply=migrate_004_travel,
),
```

Also update the fresh database definitions in `database/setup.py`. New installations should begin with the latest schema, while migrations upgrade existing installations.

## Migration rules

- Never edit or renumber an applied migration.
- Create a new migration for every later schema change.
- Never delete and recreate the player database to apply an update.
- Preserve existing player data.
- Use safe defaults when adding required columns.
- Backfill existing rows when a new field cannot remain `NULL`.
- Keep migrations separate from terminal and gameplay code.
- Make every migration safe inside a database transaction.
- Test migration from an older schema.
- Test that running migrations twice changes nothing.
- Back up production data before deploying schema changes.

## Verification

Run migration tests:

```bash
python3 -m unittest discover \
    -s tests \
    -p "test_migrations.py" \
    -v
```

Run the complete test suite:

```bash
python3 -m unittest discover -s tests -v
```

Inspect the active schema version:

```bash
sqlite3 data/game.db "
SELECT version, name, applied_at
FROM schema_migrations
ORDER BY version;
"
```