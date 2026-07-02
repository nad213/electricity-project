# Pipeline ETL

Trois lambdas Python 3.12 (`infrastructure/lambdas/`), déclenchées par CloudWatch Events, écrivent des Parquet dans un bucket S3 unique. Provisionnement : Terraform (`infrastructure/terraform/`).

## Organisation du bucket S3

Bucket `elec-app-<suffixe aléatoire>` (nom généré par Terraform), région `eu-west-3` :

```
01_downloaded/          # données brutes telles que téléchargées
  odre/                 #   exports Parquet ODRE (TR + consolidé)
  portail_analyse_et_donnees/   # scraping RTE (éolien/solaire)
02_clean/               # données transformées, lues par la webapp
state/                  # état interne (fraîcheur ODRE)
logs/                   # download_log.csv (métadonnées de chaque ingestion)
```

## Lambda `01_odre_eco2mix` — cœur du pipeline

Déclencheur : `rate(1 hour)`. Timeout 300 s / 2048 MB.

1. **Download conditionnel** : pour chaque dataset ODRE (`eco2mix-national-tr`, `eco2mix-national-cons-def`), lit la métadonnée `data_processed` via l'API catalogue (sans télécharger le fichier) et la compare à l'état stocké dans `state/odre_freshness.json`. Si rien n'a bougé → la lambda s'arrête là (no-op, pas de transform). L'état n'est mis à jour qu'**après** un upload réussi.
   ⚠️ Utiliser `data_processed` (bouge à chaque refresh du dataset), pas `modified` (date de modif des métadonnées, figée).
2. **Download** des exports Parquet ODRE qui ont changé → `01_downloaded/odre/`.
3. **Transform** en trois familles (conso, production, échanges), chacune produisant 3 fichiers dans `02_clean/` :

| Famille | Détail (pas 15/30 min) | Mensuel | Annuel |
|---|---|---|---|
| Consommation | `consommation_france_puissance.parquet` | `consommation_mensuelle.parquet` | `consommation_annuelle.parquet` |
| Production | `production_france_detail.parquet` | `production_mensuelle.parquet` | `production_annuelle.parquet` |
| Échanges | `echanges_france_detail.parquet` | `echanges_mensuels.parquet` | `echanges_annuels.parquet` |

Chaque transform applique le même schéma :

- **Fusion TR / consolidé** : sur les horodatages communs, le consolidé gagne ; le temps réel ne sert qu'au-delà. Colonne `source` = `Consolidated Data` ou `Real-Time Data`.
- **`merge_with_existing`** : le nouveau DataFrame est fusionné avec le fichier S3 existant — le nouveau a priorité, l'ancien comble les trous (ODRE purge son historique, on le conserve ainsi indéfiniment).
- **`prune_realtime_in_consolidated_zone`** : supprime tout point temps réel situé avant la frontière du consolidé (voir [03-donnees.md](03-donnees.md#temps-réel-vs-consolidé) pour le pourquoi).
- **Agrégation énergie** : somme des puissances divisée par 2 (consolidé, pas 30 min) ou 4 (TR, pas 15 min) → MWh, **avant** de sommer les deux sources.

4. **Log** : métadonnées de chaque ingestion (nb lignes, bornes de dates, taille) appendées dans `logs/download_log.csv`.

## Lambda `02_scrape_rte_production`

Déclencheur : cron 07:00 UTC. Timeout 120 s / 512 MB.

Scrape les pages RTE `analysesetdonnees.rte-france.com/production/{eolien,solaire}` : extrait les blobs `JSON.parse('…')` embarqués dans le HTML, puis reconstruit des séries mensuelles. Sorties dans `01_downloaded/portail_analyse_et_donnees/` :

- `rte_eolien_production_mensuelle.parquet`, `rte_solaire_production_mensuelle.parquet` (`date`, `filiere`, `valeur_mwh` — valeurs source en TWh, multipliées par 10⁶)
- `rte_eolien_facteur_charge_mensuel.parquet`, `rte_solaire_facteur_charge_mensuel.parquet` (`date`, `type`, `facteur_charge_pct` ; pour l'éolien, la distinction terrestre/en mer est reconstruite depuis les clés du blob, les noms étant génériques)

Fragile par nature (structure HTML/JS non contractuelle) : la lambda logue les clés des blobs trouvés pour diagnostiquer un changement de page.

## Lambda `03_rte_pmax`

Déclencheur : cron 07:05 UTC. Timeout 60 s / 256 MB.

Récupère le JSON de puissance maximale installée par filière (endpoint CloudFront du site RTE) → `02_clean/rte_pmax.parquet` (`filiere`, `puissance_max_mw`). Les catégories RTE sont traduites en français et une ligne synthétique `Hydraulique (total)` est ajoutée (somme fil de l'eau + STEP + lacs).

## Terraform

- **State** : backend S3 (`electricity-terraform-state`, `eu-west-3`).
- **Ressources** : bucket S3 + « dossiers », 3 fonctions Lambda, 3 règles CloudWatch Events, rôle/policy IAM commun (accès S3 dont `state/*`, logs CloudWatch).
- **Layer** : AWS SDK Pandas (Python 3.12) pour les trois lambdas.
- **Packaging** : `bash zip_lambda.sh` (depuis `infrastructure/terraform/`) puis `terraform apply`.

```bash
cd infrastructure/terraform
bash zip_lambda.sh
terraform plan
terraform apply
```

Test local des lambdas : `python run_lambdas_local.py` à la racine.
