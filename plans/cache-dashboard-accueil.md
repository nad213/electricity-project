# Plan : Cache du dashboard de l'accueil

## Objectif

L'accueil SSR est l'endpoint le plus coûteux de la webapp (~1 s CPU :
`get_dashboard_data` ~590 ms + `get_echanges_annual_import_export` ~420 ms +
`get_echanges_net_by_border` + parc installé — cf.
`notes/capacite_charge_clever_2026-07-18.md`). Il est identique pour tous les
visiteurs (aucun paramètre). Mettre le **contexte calculé** en cache pour que
seul le premier visiteur après chaque rafraîchissement de données paie le
calcul.

## Approche

Cacher le dict `context` (pas la réponse HTTP : la navbar dépend de la session
utilisateur, le template continue d'être rendu à chaque requête — c'est
négligeable).

- **Clé** = date locale du jour + ETags des 9 Parquet sources de l'accueil
  (déjà présents dans les `.meta.json` du cache Parquet). Nouvel ETL ⇒ nouvel
  ETag ⇒ nouvelle clé ⇒ recalcul auto. La date dans la clé évite de servir la
  « photo du jour » de la veille après minuit (les requêtes utilisent
  CURRENT_DATE).
- **TTL 1 h** en filet de sécurité.
- **Backend** = cache Django `default` (LocMem). Par process, mais la prod
  tourne mono-worker — si multi-workers un jour, chaque worker recalcule une
  fois, sans incohérence.
- Ne pas cacher le contexte vide (échec S3) pour ne pas figer une page en
  panne.

## Étapes

1. `data_cache.py` : helper public `get_etag(key)` (lecture du `.meta.json`,
   sans appel S3).
2. `views.py` (`accueil`) : lookup cache avant le bloc de calcul, `cache.set`
   après si le contexte est non vide.
3. Tests (`tests.py`) : 2e requête ne recalcule pas (mock des services),
   changement d'ETag ⇒ recalcul, contexte vide non caché.
4. `docs/04-webapp.md` : documenter le cache (même commit).

## Fichiers concernés

- `webapp/consommation/data_cache.py`
- `webapp/consommation/views.py`
- `webapp/consommation/tests.py`
- `docs/04-webapp.md`

## Risques / points d'attention

- La clé lit 9 fichiers `.meta.json` par requête : coût ~µs, OK.
- Si un `.meta.json` manque (fallback S3 direct), ETag `''` ⇒ la clé reste
  stable ⇒ le TTL 1 h prend le relais. Acceptable.
- Le refresh Parquet en fond (thread périodique, commit 0a91850) met à jour
  les `.meta.json` ⇒ l'invalidation par ETag suit le rythme réel des données.
- Objets du contexte (datetime, str JSON Plotly, SVG) : tous picklables.
