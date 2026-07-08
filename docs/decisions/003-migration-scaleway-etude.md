# ADR 003 — Migration vers Scaleway (cloud souverain)

**Statut : remplacé** — l'étude a débouché sur deux décisions : webapp sur Clever Cloud ([ADR 004](004-hebergement-clever-cloud.md)), ETL sur Scaleway Functions ([ADR 005](005-migration-etl-scaleway.md)). (Analyse du 2026-06-18.)

## Contexte

Le stack actuel est Render (webapp) + AWS (Lambda, S3, région Paris). Question explorée : le remplacer par un cloud souverain européen, avec un équivalent FaaS pour ne pas réintroduire de serveurs à gérer pour l'ETL.

## Analyse (résumé)

- **Scaleway** est le seul souverain européen avec un FaaS mature couvrant tous les besoins : Serverless Functions + cron (remplace Lambda/CloudWatch), Serverless Containers ou Instance (remplace Render), Object Storage S3-compatible, Postgres managé, provider Terraform officiel (réécriture ~1:1).
- Les autres (OVHcloud, Outscale, Clever Cloud, Infomaniak/Exoscale) n'ont pas de FaaS managé.
- Migration « d'emballage, pas de code » : la logique ETL et la webapp ne changent pas.
- Budget estimé : **~20–27 €/mois**, dominé par le Postgres managé (~11 €).
- Nuance : Scaleway est hors Cloud Act mais son cloud public n'est **pas** qualifié SecNumCloud.

## Décision

Aucune pour l'instant. L'analyse complète (correspondance des services, budget détaillé, plan de migration) est dans `notes/MIGRATION_SCALEWAY.md` et le plan d'exécution éventuel dans `plans/migration-scaleway.md`.
