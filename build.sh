#!/usr/bin/env bash
# exit on error
set -o errexit

# Install Python dependencies
pip install -r webapp/requirements.txt

# Collect static files
cd webapp
python manage.py collectstatic --no-input
