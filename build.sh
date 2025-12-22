#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r webapp/requirements.txt

cd webapp
python manage.py collectstatic --no-input
python manage.py migrate
