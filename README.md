# Buzzelec — Énergie France

Plateforme de visualisation des données électriques françaises : consommation, production par filière, échanges transfrontaliers. Application publiée sur <https://statelec.cleverapps.io/>.

Sources : **ODRE** (eco2mix temps réel + consolidé) et **RTE** (production éolien/solaire, puissance max installée).

## Architecture

```
ODRE + RTE → Lambdas ETL (AWS, eu-west-3) → S3 (Parquet) → Django + DuckDB → Plotly / API v1 / Chatbot
```

Deux composants, qui ne communiquent que par S3 :

- **`infrastructure/`** — pipeline ETL serverless : 3 lambdas Python + Terraform
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

```bash
cd infrastructure/terraform
bash zip_lambda.sh            # packager les lambdas
terraform apply
```

### Tester les lambdas en local

```bash
python run_lambdas_local.py
```

## Déploiement

- **Webapp** : Clever Cloud, auto-deploy sur push `master` (GitHub Actions → `clever deploy`)
- **Infrastructure** : `terraform apply` manuel

## Licence

Projet personnel — données publiques (ODRE / RTE).
