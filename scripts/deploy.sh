#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

echo "Creating pre-deployment database backup..."
if [[ -f ".venv/bin/python" ]]; then
    sudo -E .venv/bin/python scripts/backup_database.py
fi

echo "Updating source..."
git pull --ff-only origin main

# A rename leaves the old directory behind wherever it holds compiled
# bytecode -- git deletes the tracked files and stops there. That is
# how `tests/auth/` survived becoming `tests/authentication/` on this
# box, as an empty shell that looked like the fault it no longer was.
# Sweeping the caches keeps the tree honest about what is in it.
find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find . -depth -type d -empty -not -path "./.git/*" -delete 2>/dev/null || true

echo "Installing locked dependencies..."
.venv/bin/python -m pip install -r requirements.txt

echo "Running tests..."
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q auth database game utils web

echo "Restarting application..."
sudo systemctl restart the-smoke

echo "Checking health..."
for attempt in {1..10}; do
    if curl --fail --silent http://127.0.0.1:8001/healthz >/dev/null; then
        echo "Deployment successful."
        exit 0
    fi
    sleep 1
done

echo "Deployment failed health check." >&2
sudo systemctl status the-smoke --no-pager >&2
exit 1
