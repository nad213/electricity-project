#!/usr/bin/env bash
# Hook de build sur Clever Cloud : CC_POST_BUILD_HOOK=bash clevercloud/post_build.sh
# Équivalent de l'ancien build.sh Render (collectstatic + migrate). Les dépendances
# sont installées par le runtime Python de Clever (APP_FOLDER=webapp → requirements.txt).
set -o errexit

cd "$(dirname "$0")/../webapp"
python manage.py collectstatic --no-input
# Migrations de la base (clés d'API). Sans DATABASE_URL, Django retombe sur
# SQLite (cf. config/settings.py) — voir docs/06-deploiement.md pour la Postgres.
python manage.py migrate --no-input
