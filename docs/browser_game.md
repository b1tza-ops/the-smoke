# V1 browser game

The Flask interface exposes the completed V1 game systems through normal server-rendered pages. It deliberately calls the same services as the CLI so game rules have one source of truth.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
export THE_SMOKE_SECRET_KEY="replace-with-a-long-random-secret"
python3 app.py
```

Open <http://127.0.0.1:5000>, register an account, and create a character.

For HTTPS deployments, also set:

```bash
export THE_SMOKE_SECURE_COOKIES=1
```

## Playable systems

- Character dashboard and persistent resources
- Variable-energy gym training and district gym memberships
- District crimes with nerve, cash, XP, wanted, jail, and hospital outcomes
- Legal career, three-hour shifts, career XP, and promotions
- Persistent inventory and consumables
- Atomic bank deposits and withdrawals
- Timed London travel
- Starter housing progression

Every state-changing browser action uses a POST form with a per-session CSRF token. The browser controller validates input, calls the existing backend service, saves the player, flashes a result, and redirects so refreshing does not repeat an action.

## Tests

Run the complete suite:

```bash
python3 -m unittest discover -s tests -v
```

The browser tests cover onboarding, every V1 page, CSRF rejection, and persisted bank/gym actions.
