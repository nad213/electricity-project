# ADR 001 — Parquet sur S3 + DuckDB (pas de base de données pour les données métier)

**Statut : adopté** (en place depuis l'origine du projet ; cache local ajouté en 2026)

## Contexte

Les données (conso, production, échanges) sont mises à jour quelques fois par jour par l'ETL, lues en lecture seule par la webapp, et se prêtent à des agrégations analytiques (SQL sur colonnes). Une base relationnelle imposerait un service à administrer, des migrations de schéma et un coût fixe, pour un besoin purement lecture/agrégation.

## Décision

- L'ETL écrit des fichiers **Parquet sur S3** ; c'est le contrat entre pipeline et webapp.
- La webapp interroge ces fichiers en SQL via **DuckDB** (`services.py`).
- Un **cache local** (`data_cache.py`) télécharge chaque fichier une fois et revérifie l'ETag S3 au plus toutes les `PARQUET_CACHE_CHECK_TTL` secondes ; en cas d'erreur, fallback en lecture S3 directe (`httpfs`).

## Conséquences

- Zéro base à administrer pour les données ; le stockage coûte quelques centimes.
- Requêtes rapides (lecture disque locale) après warmup ; premier hit d'un déploiement légèrement plus lent.
- Fraîcheur bornée par le TTL du cache (1 h en prod) — acceptable vu la cadence des sources.
- Les fichiers détaillés S3 portent un historique reconstruit irremplaçable (voir [../03-donnees.md](../03-donnees.md)).

Détails d'implémentation du cache : `wiki/cache-parquet-s3.md`.
