# Plan : Supprimer les dents de scie temps-réel / consolidé (conso, production, échanges)

## Objectif

Les fichiers `02_clean/*_france_*.parquet` mélangent, dans une même série, des points
**consolidés** (pas 30 min, définitifs) et des points **temps réel** (pas 15 min,
provisoires). Les points temps réel intercalés (xx:15 / xx:45) sont systématiquement
biaisés à la baisse (~1,5 GW en moyenne sur la conso, 95 % des points sous la courbe
consolidée) → effet **dents de scie** sur les graphiques.

Décision (validée) : **ne conserver le temps réel que sur la frange récente non encore
consolidée**. Dès qu'une période dispose du consolidé (30 min), on supprime les points
temps réel ¼h de cette période. Résultat : série homogène 30 min sur tout l'historique,
15 min uniquement au-delà de la frontière du consolidé.

## Bug secondaire découvert (plus grave que le visuel)

L'agrégation mensuelle est step-aware (`conso/2` pour consolidé, `conso/4` pour RT) et
**somme l'énergie des deux séries qui se recouvrent**. Sur un même créneau horaire, le
consolidé couvre déjà toute l'heure ; les points RT ¼h rajoutent ~0,5 h d'énergie par-dessus
→ **totaux mensuels/annuels gonflés de ~+49 %** (ex. conso fév. 2026 : 59 386 GWh affichés
vs ~39 947 GWh réels). Les graphiques conso mensuelle/annuelle sont donc faux sur toute la
période de chevauchement RT/consolidé. Le prune corrige aussi ce bug (les agrégats sont
recalculés depuis `df_result` nettoyé).

## Règle retenue

Soit `cons_max = max(date_heure) des points "Consolidated Data"`.
On garde un point `"Real-Time Data"` **si et seulement si** `date_heure > cons_max`.
Tout point temps réel situé dans la zone couverte par le consolidé est supprimé.

## Étapes

1. **Lambda `01_odre_eco2mix`** (`odre_eco2mix.py`)
   - Ajouter un helper `drop_realtime_covered_by_consolidated(df_tr_unique, df_cons_def)`
     qui ne garde que les points temps réel strictement postérieurs à `cons_max`.
   - L'appeler dans `transform_conso`, `transform_production`, `transform_echanges`
     avant le `pd.concat`.
   - ✅ Fait : helper `prune_realtime_in_consolidated_zone`, appelé **après**
     `merge_with_existing` dans les 3 transforms. Comme le prune s'applique au résultat
     mergé (qui réinjecte tout l'historique consolidé), la lambda **s'auto-répare** au
     prochain run : puissance/detail + agrégats mensuels/annuels recalculés propres.

2. **Application en prod** (au choix, touche des données de prod → confirmation requise) :
   - **Option A (recommandée)** : déployer la lambda corrigée puis la déclencher une fois
     (`run_lambdas_local.py` ou trigger AWS). Recalcule tout de façon cohérente.
   - **Option B** : backfill one-shot direct sur S3 (`infrastructure/scripts/
     backfill_purge_realtime.py`) — plus rapide mais ne recalcule pas les agrégats
     mensuels/annuels, qu'il faudrait purger/recalculer séparément. Backup S3 + dry-run.

3. **Vérification** : recontrôler l'écart RT vs interpolation consolidée sur février
   (doit disparaître : plus aucun point RT dans la zone consolidée).

## Fichiers concernés

- `infrastructure/lambdas/01_odre_eco2mix/odre_eco2mix.py` (helper + 3 appels + purge post-merge)
- `infrastructure/scripts/backfill_purge_realtime.py` (nouveau, one-shot)

## Risques / points d'attention

- **Perte de granularité 15 min sur l'historique** : assumé (les points étaient biaisés).
- **Trous internes dans le consolidé** : la règle « > cons_max » suppose le consolidé
  contigu jusqu'à sa frontière ; un trou interne ferait perdre le RT correspondant.
  Acceptable vu que le jeu ODRE def est complet au pas 30 min.
- **Réécriture de fichiers de production** : backup S3 obligatoire + dry-run avant apply.
  Écriture outward-facing → confirmation utilisateur avant `--apply`.
- Vérifier que le front (Django/DuckDB) ne suppose pas un pas 15 min constant
  (cap MAX_RANGE_DAYS, resampling) — cf. [[reference_granularite_courbes]].
