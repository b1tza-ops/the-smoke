# The Smoke — Project Folder Structure

The project is organised by responsibility. New modules should be placed in the package that owns their behaviour instead of being added as loose files.

```text
the-smoke/
├── app.py                     # Stable Flask entrypoint
├── main.py                    # Stable CLI entrypoint
├── config.py
├── requirements.txt
│
├── auth/
│   ├── rate_limit.py
│   ├── validation.py
│   └── services/
│       ├── login.py
│       ├── password_reset.py
│       └── register.py
│
├── cli/
│   └── application.py
│
├── database/
│   ├── core/
│   │   ├── connection.py
│   │   ├── migrations.py
│   │   └── setup.py
│   └── repositories/
│       ├── auth_tokens.py
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
│   │   ├── definitions.py
│   │   └── service.py
│   ├── housing/
│   │   └── service.py
│   ├── inventory/
│   │   ├── items.py
│   │   └── service.py
│   ├── jobs/
│   │   ├── definitions.py
│   │   └── service.py
│   ├── player/
│   │   ├── model.py
│   │   ├── progression.py
│   │   ├── regeneration.py
│   │   └── status.py
│   └── world/
│       ├── districts.py
│       └── travel.py
│
├── landing/                   # Standalone public holding page
├── web/
│   ├── application.py
│   ├── static/
│   │   └── style.css
│   └── templates/
│       ├── dashboard.html
│       └── login.html
│
├── tests/
│   ├── auth/
│   ├── gameplay/
│   └── persistence/
│
├── utils/
└── docs/
```

Every Python package contains an `__init__.py` file.

## Entrypoints

The root files are deliberately small and stable:

- `python3 app.py` starts the Flask development server.
- `flask --app app run` can discover the exported Flask application.
- `python3 main.py` starts the command-line game.

Application logic belongs in `web/application.py` or `cli/application.py`, not in the root wrappers.

## Responsibilities

### `auth/services/`

User-facing authentication workflows such as registration, login, password recovery, validation, and rate-limit integration. Authentication uses user and account-token repositories instead of issuing SQL directly.

### `cli/`

Terminal menus and command-line orchestration. Core game rules remain in `game/`.

### `database/core/`

SQLite connection configuration, fresh-schema setup, and ordered schema migrations. Gameplay rules do not belong here.

### `database/repositories/`

Functions that load and persist users, players, balances, and other game records. SQL belongs in this layer.

### `game/`

Game definitions and rules. Package entry points such as `game.player`, `game.crime`, `game.gym`, and `game.housing` expose stable public interfaces.

### `web/`

Flask routes, Jinja templates, and browser assets. Flask automatically resolves templates and static files relative to this package.

### `landing/`

The independent static holding page used by the public site. It remains separate from the playable Flask interface.

### `tests/`

- `tests/auth/` covers authentication security and account recovery.
- `tests/gameplay/` covers game rules.
- `tests/persistence/` covers SQLite, migrations, and saved player state.

The directory names intentionally avoid `tests/game/` and `tests/database/`, which could shadow the real application packages during test discovery.

### `utils/`

Small cross-cutting helpers, including password security. A helper should only live here when it is genuinely shared.

### `docs/`

Design decisions, schema guidance, roadmap information, and architectural rules.

## Import rules

- Root entrypoints delegate immediately to `web` or `cli`.
- Entrypoints may import authentication services, repositories, and game packages.
- Authentication services use repositories for stored user data.
- Repositories use `database.core.connection` for SQLite access.
- Schema setup uses `database.core.migrations`.
- Game packages should not issue SQL directly.
- Tests must patch the module path where an object is looked up.
