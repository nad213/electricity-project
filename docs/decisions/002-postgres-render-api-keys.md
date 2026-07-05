# ADR 002 — Postgres Render pour les clés d'API

**Statut : remplacé par [ADR 004](004-hebergement-clever-cloud.md)** (juillet 2026) — la Postgres vit désormais dans un add-on Clever Cloud, ce qui règle l'échéance du free tier Render (~2026-09-03). Le raisonnement ci-dessous (« un stockage qui survit aux redéploiements ») reste valable.

## Contexte

L'API publique v1 exige des clés révocables. Les sessions étant en cookies signés, la seule donnée à persister côté serveur est la table `ApiKey` (quelques lignes : hash SHA-256, préfixe, propriétaire, dates). Le système de fichiers des services web Render est **éphémère** : un SQLite local serait perdu à chaque déploiement. Poser le fichier SQLite sur S3 est exclu (pas de locking → corruption).

## Décision

Réintroduire une **Postgres managée Render** (free tier), branchée via `DATABASE_URL` (dj-database-url), fallback SQLite en local. L'ORM Django est conservé tel quel.

## Conséquences

- Zéro code spécifique ; migrations Django standard.
- La base est très surdimensionnée pour quelques lignes — le vrai besoin est « un stockage qui survit aux redéploiements ».
- **Échéance** : free tier expire vers 2026-09-03 (+ rotation du mot de passe à prévoir). Alternatives analysées dans `notes/db_api_keys_options.md` (disque persistant Render, Litestream, DynamoDB, Neon/Supabase) — décision de remplacement non prise.
