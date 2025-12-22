# Electricity Project - Énergie France

Projet unifié pour la visualisation des données de consommation et production électrique en France.

## Architecture

```
electricity-project/
├── infrastructure/          # Infrastructure AWS (Terraform + Lambdas)
│   ├── terraform/          # Configuration Terraform
│   └── lambdas/            # Fonctions Lambda Python
├── webapp/                 # Application web Django
│   ├── config/            # Configuration Django
│   ├── consommation/      # App Django principale
│   ├── templates/         # Templates HTML
│   └── static/            # Fichiers CSS/JS
└── scripts/               # Scripts utilitaires
```

## Flux de données

```
Cron CloudWatch (quotidien 6h UTC)
    ↓
Lambda 00: csv_to_sqs
    → Envoie les URLs des CSVs dans une queue SQS
    ↓
Lambda 01: downloader
    → Télécharge les CSVs depuis l'API data.gouv.fr
    → Stocke dans S3 (raw data)
    ↓
Lambda 02: transform (7h UTC)
    → Transforme les CSVs en Parquet
    → Agrège par période (puissance, mensuel, annuel)
    → Stocke dans S3 (processed data)
    ↓
Django Web App
    → Lit les Parquet depuis S3
    → Affiche graphiques interactifs (Plotly)
```

## Infrastructure AWS

### Ressources déployées

- **S3 Bucket** : Stockage des données brutes (CSV) et transformées (Parquet)
- **SQS Queue** : Queue de téléchargement
- **3 Lambda Functions** :
  - `00_csv_to_sqs` : Initialise les téléchargements
  - `01_downloader` : Télécharge les fichiers CSV
  - `02_transform_conso_france` : Transforme les données de consommation
  - `02_transform_production_france` : Transforme les données de production
- **CloudWatch Events** : Déclencheurs quotidiens (cron)

### Déploiement infrastructure

```bash
cd infrastructure/terraform

# Initialiser Terraform
terraform init

# Vérifier le plan
terraform plan

# Déployer
terraform apply
```

### Construction des Lambdas

```bash
cd infrastructure/terraform

# Build tous les packages Lambda
./zip_lambda.sh
```

## Application Web Django

### Installation locale

```bash
cd webapp

# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate sur Windows

# Installer les dépendances
pip install django plotly boto3 python-dotenv pandas pyarrow

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos clés AWS

# Lancer le serveur de développement
python manage.py runserver
```

### Configuration

Créer un fichier `.env` dans `webapp/` :

```env
AWS_S3_REGION=eu-west-3
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
S3_PATH_PUISSANCE=s3://your-bucket/consommation_france_puissance.parquet
S3_PATH_ANNUEL=s3://your-bucket/consommation_annuelle.parquet
S3_PATH_MENSUEL=s3://your-bucket/consommation_mensuelle.parquet
```

## Technologies utilisées

### Infrastructure
- **Terraform** : Infrastructure as Code
- **AWS Lambda** : Traitement serverless
- **Python 3.9** : Runtime Lambda
- **Pandas** : Transformation des données
- **Boto3** : SDK AWS pour Python

### Application Web
- **Django 6.0** : Framework web
- **Plotly** : Graphiques interactifs
- **Pandas** : Manipulation de données
- **PyArrow** : Lecture de fichiers Parquet

## Sources de données

Données issues de [data.gouv.fr](https://www.data.gouv.fr) :
- eCO2mix national consolidé (consommation)
- eCO2mix national temps réel (consommation)
- Production par filière

## Structure des données

### Consommation puissance
- `date_heure` : Date et heure
- `consommation` : Puissance en MW
- `source` : "Données Consolidées" ou "Temps Réel"

### Consommation annuelle
- `annee` : Année
- `consommation_annuelle` : Total en MWh

### Consommation mensuelle
- `annee_mois_str` : Format "2024-01"
- `consommation_mensuelle` : Total en MWh

## Développement

### Prérequis

- Python 3.9+
- Terraform 1.0+
- AWS CLI configuré
- Compte AWS avec permissions appropriées

### Variables d'environnement

Les clés AWS doivent être configurées :
- Via `.env` pour Django
- Via AWS CLI ou variables d'environnement pour Terraform

## Licence

Projet personnel - Données publiques
