#!/usr/bin/env bash
# Idempotent dependency + database setup for the production-planning ERP.
# Safe to run repeatedly: it recreates the virtualenv only when missing and
# always refreshes dependencies, applies migrations, and seeds demo data.
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

# Apply migrations (SQLite by default; no external services required).
python manage.py migrate --noinput

# Collect static assets for WhiteNoise.
python manage.py collectstatic --noinput

# Seed demo master data, users and sample records (idempotent).
python manage.py seed_demo

echo "Install complete. Start the dev server with: source .venv/bin/activate && python manage.py runserver 0.0.0.0:8000"
