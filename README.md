# ElecStat — Énergie France

Plateforme de visualisation des données électriques françaises : consommation, production par filière, échanges transfrontaliers. Application publiée sur <https://statelec.cleverapps.io/>.

Sources : **ODRE** (eco2mix temps réel + consolidé) et **RTE** (production éolien/solaire, puissance max installée).

## Architecture

```
ODRE + RTE → Scaleway Functions (cron, fr-par) → Object Storage (Parquet) → Django + DuckDB → Plotly / API v1 / Chatbot
```

Deux composants, qui ne communiquent que par le stockage objet (S3-compatible) :

- **`infrastructure/`** — pipeline ETL serverless : 3 Scaleway Functions Python + Terraform (`terraform-scaleway/`)
- **`webapp/`** — application Django : visualisations, API publique (`/api/v1/docs`), chatbot

## Documentation

La documentation technique complète est dans [`docs/`](docs/README.md) :
architecture, pipeline ETL, pièges métier des données, webapp, API, déploiement, décisions d'architecture.

## Démarrage rapide

### Webapp en local

```bash
cd webapp
cp .env.example .env          # première fois : remplir les variables
python -m venv venv && venv/bin/pip install -r requirements.txt
venv/bin/python manage.py runserver 8000
```

### Infrastructure

Le stack se déploie tout seul : un push sur `master` touchant `infrastructure/**`
déclenche le workflow GitHub Actions (packaging des functions + `terraform apply`).
Apply manuel possible :

```bash
cd infrastructure/terraform-scaleway
bash package_functions.sh     # packager les functions (obligatoire avant apply)
terraform apply
```

Détail (state distant, credentials, invocation manuelle des functions) :
[`docs/02-pipeline-etl.md`](docs/02-pipeline-etl.md) et [`docs/06-deploiement.md`](docs/06-deploiement.md).

## Déploiement

- **Webapp** : Clever Cloud, auto-deploy sur push `master` (GitHub Actions → `clever deploy`)
- **Infrastructure** : auto-deploy sur push `master` touchant `infrastructure/**` (GitHub Actions → `terraform apply`)

## Licence

Projet personnel — données publiques (ODRE / RTE).
