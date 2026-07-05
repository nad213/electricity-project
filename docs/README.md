# Documentation technique

Documentation de référence du projet. Chaque fichier est autonome ; l'ordre suggéré de lecture est l'ordre numérique.

| Fichier | Contenu |
|---|---|
| [01-architecture.md](01-architecture.md) | Vue d'ensemble : composants, flux de données, technologies |
| [02-pipeline-etl.md](02-pipeline-etl.md) | Les 3 lambdas AWS, déclencheurs, organisation S3, Terraform |
| [03-donnees.md](03-donnees.md) | Sources de données, schémas Parquet, pièges métier |
| [04-webapp.md](04-webapp.md) | Application Django : pages, cache Parquet, sessions, auth, chatbot |
| [05-api.md](05-api.md) | API publique v1 : endpoints, authentification, limites |
| [06-deploiement.md](06-deploiement.md) | Déploiement Clever Cloud + Terraform, variables d'environnement |
| [decisions/](decisions/) | Décisions d'architecture (ADRs), datées |

## Conventions

- La doc décrit **l'existant sur `master`** ; toute évolution de code qui la contredit doit la mettre à jour dans le même commit.
- Les analyses exploratoires et audits ponctuels vivent dans `notes/` ; les plans de tâches dans `plans/`. Quand une exploration débouche sur une décision, elle est résumée dans `docs/decisions/`.
