# Production operations

The production service reads environment variables from
`/etc/the-smoke.env`.

Recommended values:

```dotenv
THE_SMOKE_SECRET_KEY=replace-with-a-long-random-value
THE_SMOKE_DB_PATH=/opt/the-smoke/database/data/game.db
THE_SMOKE_BACKUP_DIR=/var/backups/the-smoke
THE_SMOKE_LOG_PATH=/var/log/the-smoke/app.log
THE_SMOKE_COOKIE_SECURE=1
THE_SMOKE_MAINTENANCE=0
THE_SMOKE_ADMIN_USERNAME=replace-with-a-private-admin-name
THE_SMOKE_ADMIN_PASSWORD_HASH=replace-with-a-bcrypt-hash
```

## Configure the admin panel

Generate the admin password hash interactively on the VPS so the
plain-text password never enters Git or shell history:

```bash
cd /opt/the-smoke
source .venv/bin/activate
python -c "from getpass import getpass; from utils.security import hash_password; print(hash_password(getpass('Admin password: ')))"
```

Copy the resulting hash and a private username into
`/etc/the-smoke.env`, restart the service, then visit
`https://play.the-smoke.com/admin/login`.

These credentials sign you in as the **server operator**: full
administrator authority, not tied to any player account. Moderation
actions taken this way are recorded in the audit trail as
"Server operator" rather than a named person.

## Grant staff roles

Staff can also sign in at `/admin/login` with their own game account
username and password, provided their account has a staff role. Use the
operator credentials above once to grant the first role, then let people
use their own accounts so the audit trail names them.

On a player's record page (`/admin/users/<id>`), the Moderation panel
has an "Assign role" control:

- `moderator` — warn, suspend, and restore accounts.
- `admin` — the above, plus banning, role changes, granting items, and
  forcing jail/hospital.

The last active administrator cannot demote, suspend, or ban
themselves. Suspended and banned accounts cannot sign in to the game or
to operations.

## Prepare runtime directories

```bash
sudo install -d -o ubuntu -g ubuntu /var/backups/the-smoke
sudo install -d -o ubuntu -g ubuntu /var/log/the-smoke
```

## Enable daily verified backups

```bash
sudo cp deployment/the-smoke-backup.service /etc/systemd/system/
sudo cp deployment/the-smoke-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now the-smoke-backup.timer
sudo systemctl start the-smoke-backup.service
sudo systemctl status the-smoke-backup.service --no-pager
sudo systemctl list-timers the-smoke-backup.timer
```

Fourteen backups are retained by default. Test restoration by copying
a backup to a temporary path and running:

```bash
sqlite3 /tmp/the-smoke-restore.db "PRAGMA integrity_check;"
```

### Never copy `game.db` on its own

The database runs in write-ahead logging mode, so a committed write
lives in `game.db-wal` until SQLite folds it into the main file. Copying
`game.db` alone — with `cp`, `rsync`, or a filesystem snapshot taken
mid-write — silently loses the most recent play, and you only find out
on the day you restore.

`scripts/backup_database.py` is safe: it uses SQLite's online backup
API, which reads through a connection and so includes the WAL. Use it,
or `sqlite3 game.db ".backup out.db"`, for every copy. If you must move
the files by hand, stop the service first and take `game.db`,
`game.db-wal` and `game.db-shm` together.

## Deploy

```bash
cd /opt/the-smoke
bash scripts/deploy.sh
```

The deployment backs up the database, fast-forwards `main`, installs
dependencies, runs tests, compiles Python files, restarts Gunicorn and
checks `http://127.0.0.1:8001/healthz`.

## Maintenance mode

Set `THE_SMOKE_MAINTENANCE=1` in `/etc/the-smoke.env`, then restart
the service. The public game returns a maintenance page with HTTP 503,
while `/healthz` remains available. Set it back to `0` and restart
to reopen the game.

## Logs and health

Application logs rotate at 5 MB with five retained files:

```bash
sudo tail -f /var/log/the-smoke/app.log
curl --fail http://127.0.0.1:8001/healthz
```

Sensitive POST routes are rate-limited per Cloudflare client IP:
login, registration, password recovery and verification resends.
