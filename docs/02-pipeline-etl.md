# Pipeline ETL

Trois fonctions Python 3.12 (`infrastructure/lambdas/` — le nom du dossier date de l'époque AWS), déclenchées par cron sur **Scaleway Functions** (namespace `elec-etl`, région `fr-par`), écrivent des Parquet dans un bucket Object Storage unique. Provisionnement : Terraform (`infrastructure/terraform-scaleway/`).

> **Historique** : le pipeline tournait sur AWS Lambda (`eu-west-3`) jusqu'au 2026-07-08 — voir [decisions/005-migration-etl-scaleway.md](decisions/005-migration-etl-scaleway.md). Le stack AWS a été démantelé le 2026-07-16 (destroy Terraform, buckets supprimés) ; un dump final du bucket données est archivé sur `s3://elec-app-scw/archive/aws-final-dump-2026-07-16.tar.gz`.

## Organisation du bucket

Bucket `elec-app-scw` (Scaleway Object Storage, S3-compatible, endpoint `https://s3.fr-par.scw.cloud`) :

```
01_downloaded/          # données brutes telles que téléchargées
  odre/                 #   exports Parquet ODRE (TR + consolidé)
  portail_analyse_et_donnees/   # scraping RTE (éolien/solaire)
02_clean/               # données transformées, lues par la webapp
state/                  # état interne (fraîcheur ODRE)
logs/                   # download_log.csv (métadonnées de chaque ingestion)
```

## Function `odre-eco2mix` (`01_odre_eco2mix`) — cœur du pipeline

Déclencheur : cron `0 * * * *` (horaire). Timeout 300 s / 2048 MB.

1. **Download conditionnel** : pour chaque dataset ODRE (`eco2mix-national-tr`, `eco2mix-national-cons-def`), lit la métadonnée `data_processed` via l'API catalogue (sans télécharger le fichier) et la compare à l'état stocké dans `state/odre_freshness.json`. Si rien n'a bougé → la fonction s'arrête là (no-op, pas de transform). L'état n'est mis à jour qu'**après** un upload réussi.
   ⚠️ Utiliser `data_processed` (bouge à chaque refresh du dataset), pas `modified` (date de modif des métadonnées, figée).
2. **Download** des exports Parquet ODRE qui ont changé → `01_downloaded/odre/`.
3. **Transform** en trois familles (conso, production, échanges), chacune produisant 3 fichiers dans `02_clean/` :

| Famille | Détail (pas 15/30 min) | Mensuel | Annuel |
|---|---|---|---|
| Consommation | `consommation_france_puissance.parquet` | `consommation_mensuelle.parquet` | `consommation_annuelle.parquet` |
| Production | `production_france_detail.parquet` | `production_mensuelle.parquet` | `production_annuelle.parquet` |
| Échanges | `echanges_france_detail.parquet` | `echanges_mensuels.parquet` | `echanges_annuels.parquet` + `echanges_annuels_import_export.parquet` |

Les agrégats mensuels/annuels des échanges somment des valeurs **signées** (positif = import) : import et export s'y annulent. `echanges_annuels_import_export.parquet` les sépare (colonnes `{total|ech_comm_*}_{import|export}_mwh`, énergie = puissance × durée réelle du pas plafonnée à 1 h, « total » sommé au pas de temps avant séparation — deux frontières opposées se compensent). Il alimente le graphe annuel de la page Échanges et le solde de l'accueil sans recalcul sur le détail (fallback webapp sur le calcul détaillé si le fichier manque).

Chaque transform applique le même schéma :

- **Fusion TR / consolidé** : sur les horodatages communs, le consolidé gagne ; le temps réel ne sert qu'au-delà. Colonne `source` = `Consolidated Data` ou `Real-Time Data`.
- **`merge_with_existing`** : le nouveau DataFrame est fusionné avec le fichier S3 existant — le nouveau a priorité, l'ancien comble les trous (ODRE purge son historique, on le conserve ainsi indéfiniment).
- **`prune_realtime_in_consolidated_zone`** : supprime tout point temps réel situé avant la frontière du consolidé (voir [03-donnees.md](03-donnees.md#temps-réel-vs-consolidé) pour le pourquoi).
- **Agrégation énergie** : somme des puissances divisée par 2 (consolidé, pas 30 min) ou 4 (TR, pas 15 min) → MWh, **avant** de sommer les deux sources.

4. **Log** : métadonnées de chaque ingestion (nb lignes, bornes de dates, taille) appendées dans `logs/download_log.csv`.

## Function `scrape-rte-production` (`02_scrape_rte_production`)

Déclencheur : cron 07:00 UTC. Timeout 120 s / 512 MB.

Scrape les pages RTE `analysesetdonnees.rte-france.com/production/{eolien,solaire}` : extrait les blobs `JSON.parse('…')` embarqués dans le HTML, puis reconstruit des séries mensuelles. Sorties dans `01_downloaded/portail_analyse_et_donnees/` :

- `rte_eolien_production_mensuelle.parquet`, `rte_solaire_production_mensuelle.parquet` (`date`, `filiere`, `valeur_mwh` — valeurs source en TWh, multipliées par 10⁶)
- `rte_eolien_facteur_charge_mensuel.parquet`, `rte_solaire_facteur_charge_mensuel.parquet` (`date`, `type`, `facteur_charge_pct` ; pour l'éolien, la distinction terrestre/en mer est reconstruite depuis les clés du blob, les noms étant génériques)

Fragile par nature (structure HTML/JS non contractuelle) : la fonction logue les clés des blobs trouvés pour diagnostiquer un changement de page.

## Function `rte-pmax` (`03_rte_pmax`)

Déclencheur : cron 07:05 UTC. Timeout 60 s / 256 MB.

Récupère le JSON de puissance maximale installée par filière (endpoint CloudFront du site RTE) → `02_clean/rte_pmax.parquet` (`filiere`, `puissance_max_mw`). Les catégories RTE sont traduites en français et une ligne synthétique `Hydraulique (total)` est ajoutée (somme fil de l'eau + STEP + lacs).

## Terraform (`infrastructure/terraform-scaleway/`)

- **State** : **local** (`terraform.tfstate` dans le dossier) — seule trace des ressources live sur une machine éphémère (Codespace) : **le sauvegarder après chaque apply** vers `s3://elec-app-scw/state/` (consigne détaillée en tête de `main.tf`).
- **Ressources** : bucket Object Storage, namespace `elec-etl`, 3 functions (`for_each`), 3 crons. Privacy `private`, `max_scale = 1` (pas d'exécutions concurrentes).
- **Auth** : env vars `SCW_*` + `TF_VAR_s3_access_key` / `TF_VAR_s3_secret_key` (cf. `.env` local, non versionné). Les creds S3 sont injectés dans l'environnement des functions (boto3 les lit via `AWS_*`).
- **Packaging** : `bash package_functions.sh` **obligatoire avant apply** — vendore les dépendances **à la racine de chaque zip** (le runtime met le dossier de déploiement sur `sys.path`, pas un sous-dossier), versions pinnées dans `requirements-functions.txt`.
- ⚠️ **Runtime musl (Alpine)** : le Python 3.12 de Scaleway Functions est compilé contre musl, pas glibc. Les wheels à extension C (numpy, pyarrow…) doivent être **`musllinux`** — une wheel `manylinux` produit un `ImportError` au chargement, avec des messages trompeurs (« Function Handler does not exist », « No module named 'pyarrow.lib' »). `package_functions.sh` force `--platform musllinux_*`. Toute nouvelle dépendance à extension C doit exister en wheel musllinux.
- **Apply manuel uniquement** : aucun workflow CI n'applique ce stack.

```bash
cd infrastructure/terraform-scaleway
bash package_functions.sh
terraform plan
terraform apply
# puis sauvegarder terraform.tfstate (cf. main.tf)
```

- **Invoquer une function à la main** (privacy `private`) : créer un token via `POST https://api.scaleway.com/functions/v1beta1/regions/fr-par/tokens` (header `X-Auth-Token: <secret_key>`, body `{"function_id": …}`), attendre qu'il soit actif, puis `curl -H "X-Auth-Token: <token>" https://<domain_name>`.
- **Logs** : Cockpit Scaleway (Grafana) ; `logs/download_log.csv` sur le bucket trace chaque ingestion ODRE.

Test local des fonctions : `python run_lambdas_local.py` à la racine.
