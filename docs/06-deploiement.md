# Déploiement et exploitation

## Vue d'ensemble

| Composant | Où | Comment |
|---|---|---|
| Pipeline ETL (functions, bucket, crons) | Scaleway `fr-par` | push `master` (`infrastructure/**`) → GitHub Actions → `terraform apply` |
| Webapp | Clever Cloud (app `statelec`) | push `master` → GitHub Actions → `clever deploy` |
| Postgres (clés d'API) | Add-on Clever Cloud `statelec-postegredb` | `DATABASE_URL` |

## Webapp sur Clever Cloud

App `statelec` (`app_40af04af-fece-4f06-83c7-6083a2283aef`, runtime **Python**, instance XS 1 Go), domaine <https://statelec.cleverapps.io/>. Le fichier `.clever.json` à la racine lie le repo à l'app pour la CLI `clever-tools`.

> ℹ️ L'application s'appelle **ElecStat** (renommage 2026-07-07) mais les identifiants techniques gardent `statelec` : app et alias Clever, domaine `statelec.cleverapps.io`, add-on Postgres `statelec-postegredb`, service account Zitadel `statelec-account-deletion`. Renommer le domaine/l'app serait une opération console Clever séparée (+ mise à jour des redirect URIs Zitadel).

### Mécanique de déploiement

- **Auto-deploy** : le workflow `.github/workflows/webapp-deploy.yml` lance `clever deploy --alias statelec --force` sur chaque push `master` (secrets GitHub `CLEVER_TOKEN` / `CLEVER_SECRET`).
- **Deploy manuel** (contournement) : `clever deploy` depuis un clone, ou `git push clever master` si le remote git Clever est configuré. `clever restart` redéploie le même commit (utile après un changement de variable d'env).
- **Build** : le runtime Python installe `webapp/requirements.txt` (via `APP_FOLDER=webapp`), puis `CC_POST_BUILD_HOOK` exécute `clevercloud/post_build.sh` (collectstatic + migrate).
- **Run** : `CC_RUN_COMMAND=bash ../clevercloud/run.sh` → gunicorn sur le port **9000** (nginx du runtime occupe le 8080 et proxifie vers 9000). Gunicorn plutôt que le uWSGI natif : uWSGI ne lance pas les threads Python sans `enable-threads`, or le warmup du cache Parquet est un thread daemon. **2 workers × 4 threads** (gthread) : une requête lente (chat Mistral, export CSV) ne bloque pas le reste du site ; sur 1 vCPU, plus de workers n'ajouterait pas de débit. La RAM DuckDB est bornée à 256 Mo par connexion (`services.py`) pour tenir dans le 1 Go de l'XS ; `--max-requests 800` recycle les workers (fuites pandas).
- Fichiers statiques servis par WhiteNoise ; le FS est **éphémère** : le cache Parquet (`/tmp/parquet_cache`) repart de zéro à chaque déploiement (warmup automatique au démarrage), et rien d'autre ne doit être écrit sur disque.

### Pièges du runtime Python Clever (constatés)

- Les répertoires de départ **diffèrent** : les hooks (`CC_POST_BUILD_HOOK`…) partent de la **racine du repo**, la commande de run part de **`$APP_HOME/$APP_FOLDER`** (= `webapp/`) — d'où le `../` dans `CC_RUN_COMMAND` et les scripts `clevercloud/*.sh` qui font leur propre `cd` (via `dirname $0`, insensible au cwd).
- `CC_RUN_COMMAND` est `exec`-uté **sans shell** et sa tokenisation est naïve (découpage sur les espaces) : pas de `cd … && …`, pas de `$VAR`, pas de guillemets ni de `bash -c "…"` ; passer par un script committé.
- Gunicorn doit binder **9000**, pas 8080 (le « port 8080 imposé » de la doc Clever vaut pour les runtimes sans reverse-proxy intégré).

### Variables d'environnement (prod)

Posées dans la console Clever ou via `clever env` (référence locale : `webapp/.env.example`) :

- Runtime : `APP_FOLDER=webapp`, `CC_PYTHON_VERSION=3.13`, `CC_RUN_COMMAND=bash ../clevercloud/run.sh`, `CC_POST_BUILD_HOOK=bash clevercloud/post_build.sh`
- `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS` (le `CSRF_TRUSTED_ORIGINS` en découle, cf. `settings.py`)
- `AWS_S3_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — depuis la bascule du 2026-07-08 : creds **Scaleway** et région **`fr-par`** (les variables gardent leur nom `AWS_*`, boto3/DuckDB les lisent nativement)
- `AWS_S3_ENDPOINT_URL` — vide/absent = AWS ; prod : `https://s3.fr-par.scw.cloud` (Scaleway). ⚠️ `AWS_S3_REGION` doit correspondre à l'endpoint (`fr-par` pour Scaleway), sinon 403 `SignatureDoesNotMatch`
- `S3_PATH_*` — un chemin `s3://…` par fichier Parquet (puissance, annuel, mensuel, production ×3, échanges, RTE ×5) ; prod : bucket `elec-app-scw`
- `DATABASE_URL` — valeur de `POSTGRESQL_ADDON_URI` injectée par l'add-on Postgres
- `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET`
- `ZITADEL_SERVICE_TOKEN` — PAT du service user Zitadel `statelec-account-deletion` (rôle Org User Manager), active la fermeture de compte in-app (vide = bouton masqué). ⚠️ Le PAT **expire le 2033-12-07** — le renouveler dans la console Zitadel puis reposer la variable sur Clever (même piège que le token Clever)
- `MISTRAL_API_KEY`, `CHAT_MODEL` (prod : `mistral-medium-latest`)
- `PARQUET_CACHE_CHECK_TTL=3600` — filet de sécurité du chemin requête (le refresh de fond fait la fraîcheur) ; `PARQUET_CACHE_REFRESH_INTERVAL` (défaut 600) — cadence du thread de refresh
- `NINJA_NUM_PROXIES=1`, et éventuels `API_THROTTLE_*`, `API_MAX_RANGE_DAYS`

## Infrastructure ETL Scaleway (Terraform)

- **Auto-deploy** : le workflow `.github/workflows/infra-deploy.yml` packagera et appliquera le stack sur chaque push `master` touchant `infrastructure/**` (+ déclenchement manuel `workflow_dispatch`). Secrets GitHub requis : `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, `SCW_DEFAULT_PROJECT_ID`, `SCW_DEFAULT_ORGANIZATION_ID`, `TF_VAR_S3_ACCESS_KEY`, `TF_VAR_S3_SECRET_KEY` (valeurs = `.env` racine).
- **State distant** : `s3://elec-tfstate-scw/terraform-scaleway/terraform.tfstate` (bucket dédié versionné). ⚠️ Pas de lock : ne pas lancer d'apply local pendant qu'un run CI tourne.
- Apply manuel toujours possible :

```bash
cd infrastructure/terraform-scaleway
export AWS_ACCESS_KEY_ID="$TF_VAR_s3_access_key" AWS_SECRET_ACCESS_KEY="$TF_VAR_s3_secret_key"   # creds du backend
bash package_functions.sh   # packager les functions (wheels musllinux, deps à la racine des zips)
terraform plan
terraform apply
```

- Credentials : env vars `SCW_*` et `TF_VAR_s3_*` (cf. `.env` local, non versionné).
- Le déploiement d'une function = re-package + apply (le hash du zip déclenche la mise à jour ; zips non reproductibles → un run CI redéploie toujours les 3 functions).
- Détail (runtime musl, invocation manuelle, logs) : [02-pipeline-etl.md](02-pipeline-etl.md#terraform-infrastructureterraform-scaleway).

## Points d'exploitation

- **Fraîcheur des données** : la function ODRE tourne toutes les heures mais ne fait rien si `data_processed` n'a pas bougé ; la webapp voit les nouveaux fichiers au plus tard `PARQUET_CACHE_REFRESH_INTERVAL` secondes après leur écriture (thread de refresh en fond, check ETag — supporté par Scaleway Object Storage), avec `PARQUET_CACHE_CHECK_TTL` en filet de sécurité.
- **Forcer un rafraîchissement webapp** : `python manage.py refresh_data` (`--force` pour tout retélécharger) — en pratique inutile en prod, le TTL suffit.
- **Historique S3** : les fichiers `02_clean/*_detail.parquet` contiennent un historique reconstruit non re-téléchargeable (voir [03-donnees.md](03-donnees.md#historique--rétention)) — ne pas les supprimer.
- **Logs** : Cockpit Scaleway (Grafana) pour les functions ; `logs/download_log.csv` sur le bucket trace chaque ingestion ODRE ; `clever logs --alias statelec` (ou la console Clever) pour la webapp.
- **Historique** : la webapp était hébergée sur Render jusqu'en juillet 2026 — voir [decisions/004-hebergement-clever-cloud.md](decisions/004-hebergement-clever-cloud.md) (l'échéance du free tier Postgres Render, [decisions/002-postgres-render-api-keys.md](decisions/002-postgres-render-api-keys.md), est réglée par la migration). L'ETL tournait sur AWS Lambda jusqu'au 2026-07-08 — voir [decisions/005-migration-etl-scaleway.md](decisions/005-migration-etl-scaleway.md) ; le stack AWS a été démantelé le 2026-07-16 (dump final : `s3://elec-app-scw/archive/aws-final-dump-2026-07-16.tar.gz`).
