# Déploiement et exploitation

## Vue d'ensemble

| Composant | Où | Comment |
|---|---|---|
| Pipeline ETL (lambdas, S3, IAM, crons) | AWS `eu-west-3` | Terraform, apply manuel |
| Webapp | Render.com | `render.yaml`, auto-deploy sur push `master` |
| Postgres (clés d'API) | Render (managed) | `DATABASE_URL` |

## Webapp sur Render

Service `electricity-project-1` (voir `render.yaml`) :

- `branch: master`, `autoDeploy: true`, `rootDir: webapp`
- Build : `./build.sh` — Start : `gunicorn config.wsgi:application`
- Python 3.13, fichiers statiques servis par WhiteNoise
- Le FS est **éphémère** : le cache Parquet (`/tmp/parquet_cache`) repart de zéro à chaque déploiement (warmup automatique au démarrage), et rien d'autre ne doit être écrit sur disque.

### Variables d'environnement (prod)

Déclarées dans `render.yaml`, valeurs saisies dans le dashboard Render (`sync: false`) :

- `SECRET_KEY` (générée), `DEBUG=False`, `ALLOWED_HOSTS`
- `AWS_S3_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- `S3_PATH_*` — un chemin `s3://…` par fichier Parquet (puissance, annuel, mensuel, production ×3, échanges)
- `MISTRAL_API_KEY`, `CHAT_MODEL` (prod : `mistral-medium-latest`)
- `PARQUET_CACHE_CHECK_TTL=3600` — à garder un peu au-dessus de la cadence ETL
- Hors `render.yaml`, posées dans le dashboard : `DATABASE_URL` (Postgres), `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET`, et éventuels `API_THROTTLE_*`, `API_MAX_RANGE_DAYS`

Référence locale : `webapp/.env.example` (les `.env` ne sont jamais versionnés).

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
- **Logs** : CloudWatch Logs pour les lambdas ; `logs/download_log.csv` sur S3 trace chaque ingestion ODRE ; logs Render pour la webapp.
- **Échéance connue** : le free tier Postgres Render expire vers **septembre 2026** (voir [decisions/002-postgres-render-api-keys.md](decisions/002-postgres-render-api-keys.md)).
