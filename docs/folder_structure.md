# The Smoke — Backend Folder Structure

The project is organised by responsibility. New modules should be placed in the package that owns their behaviour instead of being added as loose files.

```text
the-smoke/
├── app.py
├── main.py
├── config.py
├── requirements.txt
│
├── auth/
│   └── services/
│       ├── login.py
│       ├── password_reset.py
│       └── register.py
│
├── database/
│   ├── core/
│   │   ├── connection.py
│   │   ├── migrations.py
│   │   └── setup.py
│   └── repositories/
│       ├── bank.py
│       ├── players.py
│       └── users.py
│
├── game/
│   ├── crime/
│   │   └── service.py
│   ├── economy/
│   │   └── bank.py
│   ├── gym/
│   │   └── service.py
│   ├── housing/
│   │   └── service.py
│   ├── inventory/
│   ├── jobs/
│   ├── player/
│   │   ├── model.py
│   │   ├── progression.py
│   │   ├── regeneration.py
│   │   └── status.py
│   └── world/
│       ├── districts.py
│       └── travel.py
│
├── landing/
├── static/
├── templates/
├── tests/
├── utils/
└── docs/
```

Every Python package contains an `__init__.py` file.

## Responsibilities

### `auth/services/`

User-facing authentication workflows such as registration, login, and password recovery. Authentication uses user repositories instead of issuing SQL directly.

### `database/core/`

SQLite connection configuration, fresh-schema setup, and ordered schema migrations. Gameplay rules do not belong here.

### `database/repositories/`

Functions that load and persist users, players, balances, and other game records. SQL belongs in this layer.

### `game/`

Game definitions and rules. Package entry points such as `game.player`, `game.crime`, `game.gym`, and `game.housing` expose the stable public interfaces used by the application.

### `utils/`

Small cross-cutting helpers, including password security. A helper should only live here when it is genuinely shared.

### `tests/`

Automated coverage for game rules, persistence, migrations, and integration between packages.

### `docs/`

Design decisions, schema guidance, roadmap information, and architectural rules.

## Import rules

- Entrypoints may import authentication services, repositories, and game packages.
- Authentication services use repositories for stored user data.
- Repositories use `database.core.connection` for SQLite access.
- Schema setup uses the migration runner from `database.core.migrations`.
- Game packages should not issue SQL directly.
- Tests must patch the new module path where an object is looked up.
