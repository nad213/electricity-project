#!/usr/bin/env bash
# exit on error
set -o errexit

# Install Python dependencies
pip install -r webapp/requirements.txt

# Collect static files
cd webapp
python manage.py collectstatic --no-input

# Apply database migrations (clés d'API). Sans DATABASE_URL, Django retombe sur
# SQLite (cf. config/settings.py) — voir la doc pour brancher la Postgres.
python manage.py migrate --no-input
