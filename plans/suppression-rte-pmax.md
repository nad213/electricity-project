# Plan : Suppression complète de rte_pmax (lambda 3)

## Objectif

Les données RTE pmax ne sont plus fiables (écart connu sur le solaire ~31,9 GW vs ~17 GW,
point jamais résolu) → suppression de toute la chaîne : lambda 3, terraform, usages webapp
(chatbot, dashboard, services), settings, tests et docs.

## Étapes

1. **Webapp — services.py** : supprimer `_PMAX_TO_FILIERE`, `get_parc_pmax()`, l'appel
   dans `get_dashboard_data()` (l.1013) et la clé `'parc_pmax'` du dict retourné (l.1024).
2. **Webapp — chat.py** : l'outil `get_parc` ne garde que le mode historique →
   retirer le paramètre `mode` (schema + `_tool_get_parc`), réécrire la description
   et la règle du prompt système (l.46) en conséquence.
3. **Webapp — views.py** : retirer `'rte_pmax'` de `_ACCUEIL_PARQUET_KEYS` (l.796).
4. **Webapp — settings.py / .env.example / .env local** : retirer `S3_PATH_RTE_PMAX`.
5. **Webapp — tests.py** : `ChatParcToolTests` — supprimer
   `test_actuel_renvoie_pmax_toutes_filieres` et `test_mode_inconnu_renvoie_erreur`,
   adapter les appels restants (plus de clé `mode`), mettre à jour le docstring.
6. **Infra** : supprimer `infrastructure/lambdas/03_rte_pmax/`, l'entrée `rte_pmax`
   dans `functions.tf` (+ les 2 blocs `moved` associés, commentaires 3→2 functions),
   la ligne `package_one 03_rte_pmax` de `package_functions.sh`.
7. **Docs** : `01-architecture.md` (mermaid + « trois » → « deux »),
   `02-pipeline-etl.md` (section rte-pmax, compteurs), `03-donnees.md` (ligne source,
   section « deux sources non comparables », schéma), `AGENTS.md` (composants).
8. **Vérification** : `manage.py check` + `python manage.py test consommation`.

## Fichiers concernés

- `webapp/consommation/services.py`, `chat.py`, `views.py`, `tests.py`
- `webapp/config/settings.py`, `webapp/.env.example`, `webapp/.env` (local)
- `infrastructure/lambdas/03_rte_pmax/` (suppression), `infrastructure/terraform-scaleway/functions.tf`,
  `infrastructure/terraform-scaleway/package_functions.sh`
- `docs/01-architecture.md`, `docs/02-pipeline-etl.md`, `docs/03-donnees.md`, `AGENTS.md`

## Risques / points d'attention

- **Destruction infra différée** : la function `rte-pmax` et son cron ne seront détruits
  qu'au prochain `terraform apply` (CI au push `master` touchant `infrastructure/**`).
  Les blocs `moved` des 2 functions restantes doivent être conservés.
- **Fichier résiduel** : `02_clean/rte_pmax.parquet` restera dans le bucket (plus lu par
  la webapp) — suppression manuelle optionnelle, hors scope.
- **Historique non touché** : `plans/migration-etl-scaleway.md`, `plans/documentation-technique.md`
  et `blog/plan-article-stack-europeenne.md` mentionnent pmax — documents datés, laissés tels quels.
- Le chatbot perd la capacité « puissance installée toutes filières » — voulu (données fausses).
