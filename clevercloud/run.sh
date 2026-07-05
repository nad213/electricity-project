#!/usr/bin/env bash
# Commande de run de la webapp sur Clever Cloud : CC_RUN_COMMAND=bash ../clevercloud/run.sh
# ⚠️ Contrairement aux hooks (exécutés depuis la racine du repo), la commande de run part
# de $APP_HOME/$APP_FOLDER (= webapp/), d'où le « ../ ». Elle est exec-utée sans shell et
# sa tokenisation est naïve (pas de $VAR, pas de guillemets, pas de bash -c "…") — ce
# script évite de coder en dur le chemin /home/bas/app_<id>/webapp dans la variable d'env.
# Le cd via dirname le rend insensible au cwd d'appel.
# Sur le runtime Python de Clever, nginx occupe le port 8080 et proxifie vers 9000 :
# gunicorn doit écouter sur 9000.
set -o errexit

cd "$(dirname "$0")/../webapp"
exec gunicorn config.wsgi:application --bind 0.0.0.0:9000
