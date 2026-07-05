#!/usr/bin/env bash
# Commande de run de la webapp sur Clever Cloud : CC_RUN_COMMAND=bash clevercloud/run.sh
# CC_RUN_COMMAND est exec-uté sans shell depuis la racine du repo ($APP_HOME) — ce script
# évite de coder en dur le chemin /home/bas/app_<id>/webapp dans la variable d'env.
# Sur le runtime Python de Clever, nginx occupe le port 8080 et proxifie vers 9000 :
# gunicorn doit écouter sur 9000.
set -o errexit

cd "$(dirname "$0")/../webapp"
exec gunicorn config.wsgi:application --bind 0.0.0.0:9000
