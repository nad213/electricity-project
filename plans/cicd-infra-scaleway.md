# Plan : CI/CD infra Scaleway (backend distant + workflow GitHub Actions)

## Objectif

Recréer le déploiement automatique de l'ETL supprimé avec le stack AWS (d5dfbc8) :
un push sur `master` touchant `infrastructure/**` doit packager les functions et
faire `terraform apply` sur le stack Scaleway. Prérequis : sortir le state
Terraform du Codespace (backend local → Object Storage Scaleway), sinon un
runner CI n'a pas le state.

## Étapes

1. **Bucket de state dédié** `elec-tfstate-scw` (fr-par), versioning activé,
   créé hors Terraform (évite le chicken-and-egg state ↔ bucket de state).
   Pas de versioning sur `elec-app-scw` : les Parquet y sont réécrits toutes les
   heures, versionner ce bucket ferait exploser le stockage.
2. **Backend `s3`** dans `main.tf` pointé sur `https://s3.fr-par.scw.cloud`
   (flags `skip_*` requis hors AWS, `skip_s3_checksum` pour Scaleway).
   Creds backend = `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (le backend ne
   lit pas les `TF_VAR_*`) → à exporter depuis `TF_VAR_s3_*` avant `init`.
3. **Migration** : sauvegarde du tfstate local, puis
   `terraform init -migrate-state`, vérif `terraform state list` + `plan`.
4. **Workflow** `.github/workflows/infra-deploy.yml` : push master sur
   `infrastructure/**` (+ `workflow_dispatch`) → Python 3.12,
   `package_functions.sh`, `terraform init` + `apply -auto-approve`.
   Concurrency group (pas de lock DynamoDB sur Scaleway → un seul apply à la fois).
5. **Docs** : `docs/02-pipeline-etl.md` (state distant, apply via CI),
   `docs/06-deploiement.md` (secrets GitHub), en-tête de `main.tf`.
6. **Secrets GitHub** (manuel, le token Codespace est 403 dessus) :
   `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, `SCW_DEFAULT_PROJECT_ID`,
   `SCW_DEFAULT_ORGANIZATION_ID`, `TF_VAR_S3_ACCESS_KEY`, `TF_VAR_S3_SECRET_KEY`
   (valeurs = `.env` racine).

## Fichiers concernés

- `infrastructure/terraform-scaleway/main.tf` (backend + commentaires)
- `.github/workflows/infra-deploy.yml` (nouveau)
- `docs/02-pipeline-etl.md`, `docs/06-deploiement.md`

## Risques / points d'attention

- Zips non reproductibles → chaque run CI redéploie les 3 functions même à code
  identique (déjà documenté dans `functions.tf`, sans gravité, max_scale=1).
- Pas de lock d'état (pas de DynamoDB) : ne pas lancer un apply local pendant
  qu'un run CI tourne ; le concurrency group protège côté CI seulement.
- Après migration, un apply local reste possible (mêmes env vars) mais le state
  n'est plus dans le dossier — la consigne de sauvegarde manuelle disparaît.
- Premier run CI en échec tant que les secrets GitHub ne sont pas créés.
