# Plan : Cache des réponses charts AJAX + multi-workers

## Objectif

Améliorer l'affichage des pages quand plusieurs utilisateurs consultent et
manipulent les graphiques (suite de `plans/cache-dashboard-accueil.md`, cf.
mesures dans `notes/capacite_charge_clever_2026-07-18.md`).

1. **Cache des réponses AJAX charts** : chaque ouverture de page recalcule
   DuckDB + Plotly alors que la majorité des appels sont identiques (vues par
   défaut). Clé = vue + paramètres résolus + ETags Parquet → mêmes filtres =
   servi du cache, nouvel ETL = recalcul auto.
2. **Gunicorn 2 workers × 4 threads** : aujourd'hui 1 worker sync = une seule
   requête à la fois ; un appel chat Mistral ou un export CSV fige tout le
   site. Ne monte pas le débit CPU (1 vCPU) mais supprime le blocage en tête
   de file.

## Étapes

### 1. Cache charts (`views.py`)
- Helper `_cached_charts_response(view_name, parquet_keys, params, builder)` :
  clé md5 de `vue|params triés|ETags`, TTL 1 h, cache `default` (LocMem).
- Clé sur les **paramètres résolus** (dates/filtres après session), pas le GET
  brut — deux visiteurs avec les mêmes filtres partagent l'entrée.
- Branches concernées :
  - `index` : params (start, end, dynamic_only), parquets (puissance, annuel, mensuel)
  - `production` : params (start, end, filieres, dynamic_only), parquets
    (production, production_annuel, production_mensuel + 4 RTE parc)
  - `echanges` courbe : params (start, end, pays), parquet (echanges)
  - `echanges` annuel : params (pays_annuel, min, max), parquet (echanges)
- Pas de CURRENT_DATE dans ces requêtes → pas de date du jour dans la clé.

### 2. Workers (`clevercloud/run.sh` + `services.py`)
- `gunicorn --workers 2 --threads 4 --timeout 60 --max-requests 800
  --max-requests-jitter 80` (worker class gthread implicite).
- Garde-fou RAM (XS = 1 Go, 2 process) : `SET memory_limit='256MB'` +
  `SET threads=2` dans `get_duckdb_connection()`.

### 3. Tests + doc
- Tests : même requête AJAX 2× → 1 seul calcul ; dates différentes → recalcul ;
  ETag changé → recalcul.
- `docs/04-webapp.md` (section cache) et `docs/06-deploiement.md` (run command).

## Fichiers concernés

- `webapp/consommation/views.py` — helper + 4 branches AJAX
- `webapp/consommation/services.py` — pragmas DuckDB
- `webapp/consommation/tests.py`
- `clevercloud/run.sh`
- `docs/04-webapp.md`, `docs/06-deploiement.md`

## Risques / points d'attention

- **RAM** : 2 × (~180 Mo base + DuckDB ≤ 256 Mo) — ça tient dans 1 Go tant que
  deux exports lourds ne tombent pas au même instant (DuckDB spille sur disque
  au-delà de la limite). Surveiller la RAM Clever après deploy ; repli :
  `--workers 1 --threads 8`.
- **Vérifier l'export historique complet** (`export_puissance_csv` 2012→auj.)
  après le memory_limit — cas le plus gourmand.
- Throttle API par process (×2 laxiste) : accepté, trafic API trivial.
- Cache LocMem par worker : ×2 recalculs au pire, sans incohérence.
- MAX_ENTRIES LocMem 300 × ~60 Ko de JSON ≈ 18 Mo : OK.

## Suite (étape séparée)

Pré-agrégation import/export annuel échanges dans l'ETL (~420 ms → ~15 ms,
utile pour tous les pays même hors cache) — plan à part, touche
`infrastructure/` + terraform apply manuel.
