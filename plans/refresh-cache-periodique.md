# Plan : Rafraîchissement périodique du cache Parquet (webapp)

## Objectif

Sortir le coût de rafraîchissement du cache Parquet du chemin des requêtes utilisateur.
Aujourd'hui le refresh est paresseux : la première requête après expiration de
`PARQUET_CACHE_CHECK_TTL` paie les `head_object` S3 (un par fichier consulté) et les
éventuels retéléchargements. Avec un trafic quasi nul, c'est systématiquement le même
visiteur (l'admin) qui paie. Réalise le « durcissement 2 » de
`plans/durcissement-etl-cache.md` (variante thread périodique, sans webhook ETL).

## Étapes

1. `data_cache.py` : ajouter un paramètre `force_check: bool = False` à
   `ensure_local_parquet` (et le propager depuis `refresh_all`). Quand il est vrai,
   sauter le fast path TTL et faire systématiquement le `head_object` (téléchargement
   seulement si l'ETag a changé — rien à voir avec `force=True` qui supprime tout).
2. `apps.py` : transformer le thread de warmup one-shot en boucle périodique :
   `refresh_all(force_check=True)` toutes les `PARQUET_CACHE_REFRESH_INTERVAL` secondes
   (nouveau setting, défaut 600 ; `0` = désactivé, retour au warmup one-shot).
   Premier passage immédiat (= warmup actuel), thread daemon.
3. `config/settings.py` + `.env.example` : déclarer `PARQUET_CACHE_REFRESH_INTERVAL`.
4. Doc dans le même commit : `docs/04-webapp.md` (section cache) et
   `docs/06-deploiement.md` (env vars + note fraîcheur).

## Fichiers concernés

- `webapp/consommation/data_cache.py`
- `webapp/consommation/apps.py`
- `webapp/config/settings.py`, `webapp/.env.example`
- `docs/04-webapp.md`, `docs/06-deploiement.md`

## Risques / points d'attention

- **TTL vs interval** : le TTL user-path (3600 s en prod) reste un filet de sécurité si
  le thread meurt ; la fraîcheur effective devient pilotée par l'interval (600 s).
  Chaque check réussi rafraîchit `checked_at`, donc le fast path reste chaud en continu.
- **Workers Gunicorn multiples** : chaque worker fait tourner sa boucle → `head_object`
  dupliqués toutes les 10 min. Coût S3 négligeable, re-download protégé par écriture
  atomique. Pas de mitigation nécessaire.
- Le thread est daemon : pas de blocage à l'arrêt du process.
- Ne pas casser les exclusions existantes (`migrate`, `collectstatic`, `test`, `shell`).
