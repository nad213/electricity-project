# Plan : Pré-agrégation import/export annuel des échanges (ETL)

## Objectif

`get_echanges_annual_import_export` recalcule ~420 ms sur le Parquet détail
(291 k lignes) à chaque appel non caché (graphe annuel Échanges, accueil).
L'agrégat annuel existant (`echanges_annuels.parquet`) somme des valeurs
**signées** : import et export s'y annulent — inutilisable pour ce graphe.
Produire dans l'ETL un agrégat `echanges_annuels_import_export.parquet` avec
import et export séparés, par frontière et pour le total France.

## Méthode (réplication exacte du calcul webapp)

Pour chaque colonne `ech_comm_*` (et `total` = somme des 5 à chaque pas de
temps — à calculer AU PAS DE TEMPS, pas en sommant les imports/exports par
pays, car les frontières se compensent) :

- sous-ensemble des lignes où la colonne est non nulle, trié par date ;
- `dt_h` = écart au point suivant (h), plafonné à 1 h ; dernier point = 1 h
  (sémantique LEAST de DuckDB avec NULL) ;
- énergie = Σ val×dt_h, séparée val>0 (import) / val<0 (export, en positif) ;
- groupé par année. Signe source : **positif = import** (docs/03-donnees.md).

Schéma : `year`, puis `{total|ech_comm_*}_{import|export}_mwh` (13 colonnes,
~15 lignes). `merge_with_existing` sur `year` comme les autres agrégats.

## Étapes

1. **ETL** (`01_odre_eco2mix.py`, `transform_echanges`) : bloc de calcul +
   upload du nouveau parquet.
2. **Validation locale** : script scratchpad qui exécute la nouvelle
   agrégation pandas sur le parquet détail du cache local et compare aux
   résultats de `services.get_echanges_annual_import_export` (tolérance
   flottants). Pas de `run_lambdas_local.py` (écrirait dans le bucket prod).
3. **Webapp** :
   - `settings.py` : clé S3 `echanges_annuel_imp_exp`, dérivée du chemin du
     détail si `S3_PATH_ECHANGES_ANNUELS_IMPORT_EXPORT` absent (évite de
     toucher aux env vars Clever) ;
   - `services.py` : `get_echanges_annual_import_export_agg(pays)` — lit le
     pré-agrégé ; **fallback** sur le calcul détail si fichier absent/erreur
     (transition avant le premier run ETL) ;
   - `views.py` : les 2 call sites (page Échanges plage complète, accueil
     année courante) passent sur `_agg`. Le chatbot (plages arbitraires)
     reste sur le calcul détail exact.
4. **Tests** : `_agg` lit le parquet (fixture temporaire), fallback OK.
5. **Docs** : `02-pipeline-etl.md` (tableau des fichiers), `04-webapp.md`.
6. **Déploiement ETL** : `package_functions.sh` + `terraform apply` +
   sauvegarde du tfstate (consigne main.tf). Le fichier apparaît au prochain
   refresh ODRE (cron horaire) ; d'ici là le fallback webapp sert.

## Fichiers concernés

- `infrastructure/lambdas/01_odre_eco2mix/odre_eco2mix.py`
- `webapp/config/settings.py`, `webapp/consommation/services.py`,
  `webapp/consommation/views.py`, `webapp/consommation/tests.py`
- `docs/02-pipeline-etl.md`, `docs/04-webapp.md`
- `.env.example` (documenter la nouvelle var optionnelle)

## Risques / points d'attention

- **total ≠ somme des pays** (compensation entre frontières au même pas de
  temps) — validé par le script de comparaison.
- Divergence pandas/DuckDB sur le dernier point (dt NULL → 1 h) : ~0,005 TWh,
  sous l'arrondi d'affichage ; répliqué quand même (`fillna(1.0)`).
- Runtime musl : aucune dépendance nouvelle (pandas/pyarrow déjà vendorés).
- Ordre de déploiement sans coupure : webapp d'abord (fallback), ETL ensuite.
