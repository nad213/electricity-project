# Plan : Migration ETL AWS → Scaleway (Functions + Object Storage)

> Décision du 2026-07-07. Fait suite à l'analyse `notes/MIGRATION_SCALEWAY.md` (2026-06-18)
> et remplace le volet « étape 3 / étape 4 future » de `plans/migration-scaleway.md`
> (dont les étapes 1-2 — webapp et DB — ont finalement été réalisées via Clever Cloud direct).

## Objectif

Sortir complètement d'AWS : les 3 lambdas ETL deviennent des **Scaleway Serverless
Functions** (Python, cron natif, région `fr-par`) et le bucket S3 devient un bucket
**Scaleway Object Storage**. La webapp reste sur Clever Cloud — elle change seulement
d'endpoint S3. Coût cible : ~0 € (tiers gratuits Functions + Object Storage).

Arbitrage vs Clever Tasks (discussion 2026-07-07) : Scaleway retenu pour le cron natif
(pas d'horloge à bricoler), le coût nul et le Terraform 1:1 ; en contrepartie on garde
deux fournisseurs (Clever pour la webapp, Scaleway pour l'ETL).

## Étapes

### 0. Prérequis (manuel, côté utilisateur)
- Créer un compte Scaleway + un projet (ex. `elecstat`).
- Créer une application IAM + clé API (access key / secret key) avec droits
  Object Storage + Functions sur le projet.
- Fournir les creds pour Terraform (`SCW_ACCESS_KEY`, `SCW_SECRET_KEY`,
  `SCW_DEFAULT_PROJECT_ID`, `SCW_DEFAULT_ORGANIZATION_ID`).

### 1. Code — endpoint S3 paramétrable (déployable AVANT toute bascule, rétro-compatible)
Par défaut (variable absente) le comportement AWS actuel est inchangé.

- Lambdas : les 3 `boto3.client("s3")` lisent une env var optionnelle `S3_ENDPOINT_URL`.
- Webapp :
  - `config/settings.py` : `AWS_CONFIG['endpoint_url'] = os.getenv('AWS_S3_ENDPOINT_URL')`
  - `consommation/data_cache.py:_s3_client()` : passer `endpoint_url` si défini
  - `consommation/services.py:get_duckdb_connection()` : si endpoint défini →
    `SET s3_endpoint`, `SET s3_url_style='path'` (validation anti-injection comme
    les autres SET)
- `.env.example` : documenter `AWS_S3_ENDPOINT_URL` (vide = AWS).
- Commit + déploiement webapp normal (aucun effet en prod).

### 2. Terraform Scaleway (`infrastructure/terraform-scaleway/`, nouveau dossier)
Le Terraform AWS existant reste intact jusqu'au démantèlement final.

- Provider `scaleway/scaleway`, région `fr-par`.
- `scaleway_object_bucket` (nom : `elec-app-scw` ou similaire).
- `scaleway_function_namespace` + 3 `scaleway_function` (runtime Python 3.12,
  mémoire : 2048 Mo eco2mix / 512 Mo scrape / 256 Mo pmax — pics mesurés le
  2026-07-07 : 1010 / 214 / 219 Mo) + 3 `scaleway_function_cron`
  (`0 * * * *`, `0 7 * * *`, `5 7 * * *`).
- Env vars des functions : `BUCKET_NAME`, `S3_ENDPOINT_URL=https://s3.fr-par.scw.cloud`,
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (creds Scaleway — boto3 les lit
  nativement), `AWS_DEFAULT_REGION=fr-par`.
- State Terraform : backend local pour commencer (un seul poste), bascule ultérieure
  possible vers backend s3 pointé sur Object Storage.

### 3. Packaging des functions
- Script `infrastructure/terraform-scaleway/package_functions.sh` :
  `pip install -r requirements.txt --target package/` + code + zip.
- ⚠️ Les lambdas AWS reçoivent pandas via un layer ; chez Scaleway il faut
  **vendorer pandas + pyarrow + requests** dans le zip. Limite de taille des zips
  Scaleway à vérifier — **si dépassée, basculer la function en image container**
  (supporté nativement, prévu comme plan B, ajoute un registry + Dockerfile).
- La signature `lambda_handler(event, context)` est compatible telle quelle
  (les handlers n'utilisent ni event ni context).

### 4. Amorçage du bucket — PAS de sync nécessaire
Constat (vérifié dans le code le 2026-07-07) : **les 3 pipelines sont self-healing**,
ils reconstruisent tout leur historique depuis la source, sans dépendre du contenu
préexistant du bucket. Donc **on ne sync rien** — les crons Scaleway amorcent le
bucket vide tout seuls.
- `eco2mix` télécharge `eco2mix-national-cons-def` (consolidé **depuis 2012**) + `-tr`
  (temps réel) : historique complet à la source.
- `scrape_rte_production` lit les pages RTE (`monthlyData` toutes années) → Parquet
  complet en overwrite (pas de merge).
- `rte_pmax` = snapshot puissance installée → overwrite complet.
- Le « re-download complet » au premier run n'est pas un problème, c'est le comportement
  normal. `state/odre_freshness.json` et `logs/download_log.csv` se recréent seuls
  (perte de continuité des logs = purement cosmétique, acceptée).
- Seule contrainte de timing : `scrape_rte` et `pmax` ne tournent qu'à **07:00 / 07:05
  UTC** → prod/pmax absentes du bucket tant que ce créneau n'est pas passé. Ne pas
  basculer la webapp avant que ces trois jeux soient présents.

### 5. Bascule et validation
1. `terraform apply` côté Scaleway, crons actifs → laisser les crons amorcer le bucket
   (pas de sync). Attendre qu'`eco2mix`, `scrape_rte` et `pmax` aient tourné au moins
   une fois (créneau 07:00 UTC pour les deux derniers).
2. **Couper les crons AWS** — via Terraform, PAS à la main : passer les 3
   `state = "ENABLED"` à `"DISABLED"` dans `infrastructure/terraform/lambda.tf`
   et merger sur master (le workflow `infra-deploy.yml` applique). Un disable
   console serait écrasé (retour ENABLED) au prochain apply CI déclenché par
   n'importe quel push touchant `infrastructure/` hors `terraform-scaleway/`.
3. Vérifier 24-48 h : `logs/download_log.csv` côté Scaleway avance, fraîcheur OK.
4. Bascule webapp (env vars Clever) : `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION=fr-par`,
   creds Scaleway, `S3_PATH_*` (nouveau nom de bucket). Redéploiement, recette
   des pages + API.
5. Période d'observation ~1 semaine, puis `terraform destroy` côté AWS
   (garder un dump local du bucket avant destruction).
6. Mettre à jour `docs/02-pipeline-etl.md`, `docs/06-deploiement.md`,
   `docs/01-architecture.md`, `infrastructure/CLAUDE.md` + ADR dans `docs/decisions/`.

## Avancement (2026-07-07)
- Étape 1 (endpoint S3 paramétrable) : **codée**, pas encore commitée.
- Étape 2-3 (Terraform + packaging) : **`terraform apply` fait** — 8 ressources créées
  (bucket `elec-app-scw`, namespace `elec-etl`, 3 functions + 3 crons, région `fr-par`).
- **⚠️ Piège majeur résolu — runtime MUSL.** Le runtime Python 3.12 de Scaleway
  Functions est **musl (Alpine)**, pas glibc (`EXT_SUFFIX =
  .cpython-312-x86_64-linux-musl.so`). Les wheels `manylinux` initiales n'étaient pas
  reconnues comme modules d'extension → `ImportError` numpy/pyarrow au chargement
  (« handler does not exist » / « No module named 'pyarrow.lib' »). Fix :
  `package_functions.sh` installe désormais des wheels **musllinux** (`--platform
  musllinux_1_2_x86_64 --platform musllinux_1_1_x86_64`) et vendore les deps **à la
  racine** du zip (le runtime met le dossier de déploiement sur le `sys.path`, pas un
  sous-dossier `package/`). Zips ~62 Mo, sous la limite 100 MiB.
- **Les 3 functions validées de bout en bout** (invocation manuelle via token, le
  2026-07-07) : téléchargement source → transform → écriture dans `elec-app-scw`.
  Bucket amorcé (18 objets, tous les `02_clean/*.parquet` + `state/` + `logs/`).
- Étape 4 : **supprimée** (sync inutile) — bucket déjà amorcé à la main de toute façon.
- **Revue de code (2026-07-07)** — correctifs appliqués suite au code-review de la branche :
  - `requirements-functions.txt` : versions **pinnées** (boto3 1.43.41, requests 2.34.2,
    pandas 3.0.3, pyarrow 24.0.0 — celles validées de bout en bout ; côté AWS le layer
    pinnait, ici rien ne le faisait). Cross-références ajoutées avec les
    `lambdas/*/requirements.txt` (deux sources de vérité → ImportError silencieux sinon).
  - `functions.tf` : chemins `${path.module}/build/…`, prérequis `package_functions.sh`
    documenté en tête (zips gitignorés, `filesha256` échoue en dur sinon), factorisation
    `for_each` + blocs `moved` (pas de destroy/recreate des ressources live).
  - `infra-deploy.yml` : exclusion de `infrastructure/terraform-scaleway/**` des paths.
  - `lambda.tf` AWS : `state = "ENABLED"` explicite sur les 3 event rules + procédure de
    coupure par Terraform (étape 5.2 révisée — un disable console serait écrasé par CI).
  - Webapp : validation positive de l'endpoint DuckDB (la blocklist laissait passer
    `'` et `/`) ; avertissement région/endpoint (SigV4) dans `.env.example` et
    `docs/06-deploiement.md`.
  - `main.tf` : consigne de sauvegarde du tfstate local (Codespace éphémère = seule
    copie du state des 8 ressources live).
- **Crons Scaleway validés en autonomie (2026-07-08)** : `logs/download_log.csv` montre
  des runs horaires réguliers depuis la nuit (04h → 08h UTC), les 9 parquets `02_clean/`
  régénérés à 08h00-08h01, `rte_pmax.parquet` à 07h05 (cron quotidien). Étape 5.3 OK.
- **Crons AWS coupés (2026-07-08)** : les 3 event rules de `lambda.tf` passées à
  `state = "DISABLED"`, merge sur master → apply par le workflow `infra-deploy.yml`.
- **Bascule webapp faite (2026-07-08, ~09h10 UTC)** : env vars Clever basculées via
  `clever env set` (creds Scaleway, `AWS_S3_REGION=fr-par`, `AWS_S3_ENDPOINT_URL`,
  13 × `S3_PATH_*` → `elec-app-scw`), restart OK (deployment `efa3e984`). Recette :
  toutes les pages 200, exports CSV avec données fraîches (juillet 2026) sur conso /
  production / puissance 15 min — le /tmp ayant été vidé par le restart, ces données
  ne peuvent venir que du bucket Scaleway. Aucune erreur dans les logs.
- Reste : période d'observation (~1 semaine — surveiller fraîcheur + comportement ETag
  du cache), mise à jour doc (docs/01, 02, 06, infrastructure/CLAUDE.md + ADR),
  `terraform destroy` AWS (après dump local du bucket `elec-app-804cdc84`).

## Fichiers concernés
- `infrastructure/lambdas/*/[nom].py` — client boto3 paramétrable (3 fichiers)
- `infrastructure/lambdas/01_odre_eco2mix/requirements.txt` — ajouter pandas/pyarrow
  (vendorés chez Scaleway, plus de layer)
- `webapp/config/settings.py`, `webapp/consommation/data_cache.py`,
  `webapp/consommation/services.py`, `webapp/.env.example`
- `infrastructure/terraform-scaleway/` — nouveau (main.tf, functions.tf, packaging)
- `run_lambdas_local.py` — vérifier qu'il fonctionne toujours (test local)
- `docs/*` — à la bascule (étape 5.6)

## Risques / points d'attention
- **Runtime musl (Alpine)** : wheels `musllinux` obligatoires (cf. Avancement). Toute
  dépendance à extension C ajoutée plus tard doit exister en wheel musllinux.
- **Taille du package** pandas+pyarrow vs limite zip Scaleway (100 MiB/zip) : ~62 Mo,
  OK ; plan B image container si un jour dépassé.
- **`s3_url_style='path'`** requis pour DuckDB sur endpoint non-AWS ; boto3 gère seul.
- **ETags** : le cache webapp (`data_cache.py`) compare des ETags — supportés par
  Scaleway Object Storage, à valider en recette (sinon re-download à chaque check).
- **Free tier** : largement suffisant aujourd'hui (~15 exec/jour) ; à revérifier si
  la fréquence augmente.
- **Fenêtre de double-écriture** : entre l'activation des crons Scaleway et la coupure
  des crons AWS, les deux pipelines écrivent chacun dans leur bucket — sans conflit
  (buckets séparés), mais la webapp ne doit basculer qu'après validation Scaleway.
- **Ne pas supprimer AWS avant** la période d'observation ET un dump local du bucket.
- **State Terraform Scaleway local** sur un Codespace éphémère : seule copie du state
  des ressources live → sauvegarder `terraform.tfstate` hors Codespace après chaque
  apply (cf. commentaire dans `main.tf`), ou basculer le backend tôt.
- **Pas de retry sur les crons Scaleway** (EventBridge réinvoquait 2× en cas de crash
  dur type timeout/OOM) : un échec transitoire d'un job quotidien = 24 h de données
  périmées. Accepté — pipelines self-healing, le run suivant reconstruit tout.
- **Clé API Scaleway à droits projet** dans l'env des functions (l'IAM AWS était scopée
  Get/Put sur 4 préfixes, sans delete) : à durcir plus tard avec une policy IAM
  Scaleway scopée au bucket.
