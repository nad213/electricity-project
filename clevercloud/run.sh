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
# 2 workers × 4 threads (gthread) : une requête lente (chat Mistral, export CSV)
# ne bloque plus tout le site. 1 vCPU sur XS : plus de workers n'ajouterait pas
# de débit. RAM bornée côté DuckDB (memory_limit dans services.py).
# max-requests recycle les workers (fuites mémoire pandas), jitter pour ne pas
# recycler les 2 en même temps.
exec gunicorn config.wsgi:application --bind 0.0.0.0:9000 \
  --workers 2 --threads 4 --timeout 60 \
  --max-requests 800 --max-requests-jitter 80
