# ADR 005 — Migration de l'ETL vers Scaleway Functions + Object Storage

**Statut : adopté (bascule le 2026-07-08)** — concrétise l'étude de l'[ADR 003](003-migration-scaleway-etude.md) pour le volet ETL ; complète l'[ADR 004](004-hebergement-clever-cloud.md) (webapp sur Clever Cloud) pour sortir entièrement d'AWS.

## Contexte

Après la migration de la webapp vers Clever Cloud (ADR 004), l'ETL restait le dernier composant sur AWS : 3 lambdas + bucket S3 + crons CloudWatch en `eu-west-3`. L'ADR 003 avait identifié Scaleway comme seul souverain européen avec un FaaS mature (Serverless Functions + crons + Object Storage S3-compatible + provider Terraform officiel).

## Décision

Migrer l'ETL vers **Scaleway Functions** (namespace `elec-etl`, région `fr-par`) et le stockage Parquet vers **Scaleway Object Storage** (bucket `elec-app-scw`), via un stack Terraform dédié (`infrastructure/terraform-scaleway/`, apply manuel). Le code des trois fonctions est inchangé (migration « d'emballage ») : seuls le packaging et l'injection des creds S3 diffèrent.

La webapp reste sur Clever Cloud (déjà souverain, hébergeur français) et lit le nouveau bucket via son endpoint S3-compatible (`AWS_S3_ENDPOINT_URL` + `AWS_S3_REGION=fr-par`). Le Postgres reste l'add-on Clever (pas de Postgres Scaleway : une seule table, autant la garder collée à l'app).

## Points notables de la mise en œuvre

- **Runtime musl** : le Python 3.12 de Scaleway Functions est compilé contre musl (Alpine), pas glibc. Les wheels à extension C doivent être `musllinux`, et les dépendances vendorées **à la racine du zip** — deux points non documentés par Scaleway qui ont coûté l'essentiel du temps de migration (détail : [02-pipeline-etl.md](../02-pipeline-etl.md)).
- **Pas de layer** : pandas/pyarrow sont vendorés dans chaque zip (~62 Mo, sous la limite de 100 MiB), versions pinnées dans `requirements-functions.txt`.
- **State Terraform local** : à sauvegarder vers `s3://elec-app-scw/state/` après chaque apply, tant qu'un backend distant n'est pas configuré.
- **Bascule sans big-bang** : crons Scaleway activés et validés en autonomie (2026-07-07 → 08), puis crons AWS coupés via Terraform (`state = "DISABLED"`), puis env vars webapp basculées — chaque étape réversible.

## Conséquences

- Plus aucune dépendance opérationnelle à AWS ; stack 100 % hébergeurs français (Scaleway + Clever Cloud). Nuance inchangée depuis l'ADR 003 : le cloud public Scaleway n'est pas qualifié SecNumCloud.
- Le stack AWS (`infrastructure/terraform/`) est conservé crons coupés pendant une période d'observation (~1 semaine), comme rollback. Démantèlement ensuite : dump du bucket `elec-app-804cdc84`, `terraform destroy`, suppression du workflow `infra-deploy.yml`, du bucket de state et des secrets/IAM CI (procédure : `plans/migration-etl-scaleway.md`).
- Coût : free tier Scaleway Functions largement suffisant (~15 exécutions/jour) ; Object Storage quelques centimes. Le poste principal reste la webapp Clever (~16 €/mois).
