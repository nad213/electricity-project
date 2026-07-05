# Déploiement et exploitation

## Vue d'ensemble

| Composant | Où | Comment |
|---|---|---|
| Pipeline ETL (lambdas, S3, IAM, crons) | AWS `eu-west-3` | Terraform, apply manuel |
| Webapp | Clever Cloud (app `statelec`) | push `master` → GitHub Actions → `clever deploy` |
| Postgres (clés d'API) | Add-on Clever Cloud `statelec-postegredb` | `DATABASE_URL` |

## Webapp sur Clever Cloud

App `statelec` (`app_40af04af-fece-4f06-83c7-6083a2283aef`, runtime **Python**, instance XS 1 Go), domaine <https://statelec.cleverapps.io/>. Le fichier `.clever.json` à la racine lie le repo à l'app pour la CLI `clever-tools`.

### Mécanique de déploiement

- **Auto-deploy** : le workflow `.github/workflows/webapp-deploy.yml` lance `clever deploy --alias statelec --force` sur chaque push `master` (secrets GitHub `CLEVER_TOKEN` / `CLEVER_SECRET`).
- **Deploy manuel** (contournement) : `clever deploy` depuis un clone, ou `git push clever master` si le remote git Clever est configuré. `clever restart` redéploie le même commit (utile après un changement de variable d'env).
- **Build** : le runtime Python installe `webapp/requirements.txt` (via `APP_FOLDER=webapp`), puis `CC_POST_BUILD_HOOK` exécute `clevercloud/post_build.sh` (collectstatic + migrate).
- **Run** : `CC_RUN_COMMAND=bash ../clevercloud/run.sh` → gunicorn sur le port **9000** (nginx du runtime occupe le 8080 et proxifie vers 9000). Gunicorn plutôt que le uWSGI natif : uWSGI ne lance pas les threads Python sans `enable-threads`, or le warmup du cache Parquet est un thread daemon.
- Fichiers statiques servis par WhiteNoise ; le FS est **éphémère** : le cache Parquet (`/tmp/parquet_cache`) repart de zéro à chaque déploiement (warmup automatique au démarrage), et rien d'autre ne doit être écrit sur disque.

### Pièges du runtime Python Clever (constatés)

- Les répertoires de départ **diffèrent** : les hooks (`CC_POST_BUILD_HOOK`…) partent de la **racine du repo**, la commande de run part de **`$APP_HOME/$APP_FOLDER`** (= `webapp/`) — d'où le `../` dans `CC_RUN_COMMAND` et les scripts `clevercloud/*.sh` qui font leur propre `cd` (via `dirname $0`, insensible au cwd).
- `CC_RUN_COMMAND` est `exec`-uté **sans shell** et sa tokenisation est naïve (découpage sur les espaces) : pas de `cd … && …`, pas de `$VAR`, pas de guillemets ni de `bash -c "…"` ; passer par un script committé.
- Gunicorn doit binder **9000**, pas 8080 (le « port 8080 imposé » de la doc Clever vaut pour les runtimes sans reverse-proxy intégré).

### Variables d'environnement (prod)

Posées dans la console Clever ou via `clever env` (référence locale : `webapp/.env.example`) :

- Runtime : `APP_FOLDER=webapp`, `CC_PYTHON_VERSION=3.13`, `CC_RUN_COMMAND=bash ../clevercloud/run.sh`, `CC_POST_BUILD_HOOK=bash clevercloud/post_build.sh`
- `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS` (le `CSRF_TRUSTED_ORIGINS` en découle, cf. `settings.py`)
- `AWS_S3_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `S3_PATH_*` — un chemin `s3://…` par fichier Parquet (puissance, annuel, mensuel, production ×3, échanges, RTE ×5)
- `DATABASE_URL` — valeur de `POSTGRESQL_ADDON_URI` injectée par l'add-on Postgres
- `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET`
- `MISTRAL_API_KEY`, `CHAT_MODEL` (prod : `mistral-medium-latest`)
- `PARQUET_CACHE_CHECK_TTL=3600` — à garder un peu au-dessus de la cadence ETL
- `NINJA_NUM_PROXIES=1`, et éventuels `API_THROTTLE_*`, `API_MAX_RANGE_DAYS`

## Infrastructure AWS (Terraform)

```bash
cd infrastructure/terraform
bash zip_lambda.sh     # packager les lambdas
terraform plan
terraform apply
```

- State distant : bucket `electricity-terraform-state` (`eu-west-3`).
- Credentials : AWS CLI ou variables d'environnement.
- Le déploiement d'une lambda = re-zip + apply (le hash du zip déclenche la mise à jour).

## Points d'exploitation

- **Fraîcheur des données** : la lambda ODRE tourne toutes les heures mais ne fait rien si `data_processed` n'a pas bougé ; la webapp voit les nouveaux fichiers au plus tard `PARQUET_CACHE_CHECK_TTL` secondes après leur écriture (check ETag).
- **Forcer un rafraîchissement webapp** : `python manage.py refresh_data` (`--force` pour tout retélécharger) — en pratique inutile en prod, le TTL suffit.
- **Historique S3** : les fichiers `02_clean/*_detail.parquet` contiennent un historique reconstruit non re-téléchargeable (voir [03-donnees.md](03-donnees.md#historique--rétention)) — ne pas les supprimer.
- **Logs** : CloudWatch Logs pour les lambdas ; `logs/download_log.csv` sur S3 trace chaque ingestion ODRE ; `clever logs --alias statelec` (ou la console Clever) pour la webapp.
- **Historique** : la webapp était hébergée sur Render jusqu'en juillet 2026 — voir [decisions/004-hebergement-clever-cloud.md](decisions/004-hebergement-clever-cloud.md) (l'échéance du free tier Postgres Render, [decisions/002-postgres-render-api-keys.md](decisions/002-postgres-render-api-keys.md), est réglée par la migration).
