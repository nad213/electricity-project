# Plan : documentation technique du projet

## Objectif

Créer une documentation technique consolidée dans `docs/` (Markdown + diagrammes Mermaid, versionnée avec le code), qui devienne la source de vérité sur l'architecture, le pipeline de données, les pièges métier et l'exploitation. Remettre le README à jour (il décrit encore l'ancien pipeline `00_csv_to_sqs` / `01_downloader` / SQS, disparu) et le faire pointer vers `docs/`.

## Périmètre

Documentation **descriptive de l'existant**, vérifiée contre le code actuel (`master`). Pas de refonte de code, pas de doc générée automatiquement (Sphinx, etc.).

## Structure cible

```
docs/
├── README.md               # Sommaire de la doc
├── 01-architecture.md      # Vue d'ensemble + diagramme Mermaid du flux complet
├── 02-pipeline-etl.md      # Les 3 lambdas, déclencheurs, S3, Terraform
├── 03-donnees.md           # Sources, schémas Parquet, pièges métier
├── 04-webapp.md            # Django : pages, cache données, sessions, chatbot, auth
├── 05-api.md               # API publique v1 (django-ninja) + clés self-service
├── 06-deploiement.md       # Render (webapp), Terraform (infra), env vars, région
└── decisions/              # ADRs courts, datés
    ├── 001-duckdb-parquet-s3.md
    ├── 002-postgres-render-api-keys.md
    └── 003-migration-scaleway-etude.md   (statut : non décidé)
```

## Étapes

1. Créer ce plan (fait).
2. Lecture ciblée du code pour vérifier chaque affirmation :
   - `infrastructure/terraform/*.tf` (ressources, crons : ODRE horaire, RTE prod 07:00 UTC, pmax 07:05 UTC)
   - `infrastructure/lambdas/0{1,2,3}_*/` (handlers, logique download conditionnel, fichier de fraîcheur `state/`)
   - `webapp/consommation/` : `services.py`, `data_cache.py`, `views.py`, `api.py`, `api_auth.py`, `chat.py`, `auth.py`, `models.py`
   - `webapp/config/settings.py`, `render.yaml`, `requirements.txt`
3. Consolider la matière existante (vérifier contre le code avant reprise) :
   - `wiki/cache-parquet-s3.md` → 04-webapp (cache) + ADR 001
   - `notes/api-keys-selfservice.md`, `notes/db_api_keys_options.md` → 05-api + ADR 002
   - `notes/MIGRATION_SCALEWAY.md` → ADR 003 (résumé + lien)
   - Connaissance métier (signe des échanges, granularité 15/30 min, mélange TR/consolidé) → 03-donnees
4. Rédiger les fichiers `docs/` dans l'ordre 01 → 06 puis les ADRs.
5. Réécrire `README.md` : présentation courte, quickstart, renvoi vers `docs/`.
6. Relecture de cohérence (liens internes, diagrammes Mermaid qui rendent sur GitHub).

## Fichiers concernés

- Créés : `docs/*.md`, `docs/decisions/*.md`, `plans/documentation-technique.md`
- Modifiés : `README.md`
- Lus (sources) : `infrastructure/`, `webapp/`, `notes/`, `wiki/`, `render.yaml`

## Risques / points d'attention

- **Ne rien recopier des notes sans vérifier contre le code** : plusieurs notes datent d'états intermédiaires (ex. le fix TR/consolidé était « pas encore déployé » à un moment — vérifier l'état réel).
- Ne pas documenter de secrets ni de noms de bucket/URLs sensibles ; rester au niveau des patterns (`state/`, `01_downloaded/`…).
- Le README actuel contient des schémas de données obsolètes — tout re-dériver du code, pas de l'ancien README.
- Les `CLAUDE.md` sont gitignorés : la doc ne doit pas s'appuyer dessus ni y renvoyer.
- Garder chaque fichier court (< ~150 lignes) : une doc trop longue ne sera pas maintenue.
