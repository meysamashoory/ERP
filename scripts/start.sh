#!/usr/bin/env bash
# Start the Django development server, bound to all interfaces so the app is
# reachable from a browser via the server IP (per the specification).
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source .venv/bin/activate

exec python manage.py runserver 0.0.0.0:8000
