# Plan : Démantèlement du stack AWS legacy

## Objectif

Clore la migration Scaleway (cf. `plans/migration-scaleway.md`) : détruire les
ressources AWS devenues inutiles (lambdas, bucket données, state backend) et
nettoyer le repo (Terraform AWS, workflow `infra-deploy.yml`, docs). L'ETL
tourne sur Scaleway Functions depuis le 2026-07-07, la webapp lit le bucket
Scaleway depuis le 2026-07-08, observation faite jusqu'au 2026-07-15 : plus
aucune dépendance AWS.

## Étapes

1. **Dump de sûreté** du bucket données `elec-app-804cdc84` (~62 Mo, 30 objets)
   → tar.gz archivé sur le bucket Scaleway `elec-app-scw` sous
   `archive/aws-final-dump-2026-07-16.tar.gz` (endpoint `s3.fr-par.scw.cloud`,
   creds `TF_VAR_s3_*` du `.env`).
2. **Destroy Terraform** : vider le bucket données (sinon le destroy échoue,
   pas de `force_destroy`), puis `terraform init && terraform destroy` dans
   `infrastructure/terraform/` (state backend S3 `electricity-terraform-state`).
3. **Backend state** : supprimer le bucket `electricity-terraform-state`
   (créé à la main, hors Terraform) une fois le destroy terminé.
4. **Ménage repo** (un seul commit) :
   - `git rm` `infrastructure/terraform/` (main.tf, lambda.tf, iam.tf,
     zip_lambda.sh) + suppression des fichiers locaux non trackés (tfstate,
     lock).
   - `git rm` `.github/workflows/infra-deploy.yml` (le workflow ne se
     déclenchera pas sur le push qui le supprime : GitHub lit le workflow du
     commit poussé).
   - **Garder** `infrastructure/lambdas/` (source partagée, packagée par
     `package_functions.sh` pour Scaleway) et `run_lambdas_local.py`.
   - Mettre à jour `docs/01-architecture.md`, `docs/02-pipeline-etl.md`,
     `docs/06-deploiement.md` (retrait des mentions du stack AWS legacy).
   - Mettre à jour les `CLAUDE.md` locaux (gitignorés, hors commit).

## Fichiers concernés

- Supprimés : `infrastructure/terraform/**`, `.github/workflows/infra-deploy.yml`
- Modifiés : `docs/01-architecture.md`, `docs/02-pipeline-etl.md`,
  `docs/06-deploiement.md`
- Créé : ce plan

## Risques / points d'attention

- Ne PAS stager les modifs webapp en cours (fix 429 chatbot, non commité).
- L'IAM user `terraform-admin` et ses access keys ne sont pas gérés par
  Terraform : suppression manuelle en console à faire par l'humain (ce sont
  les creds utilisés pour le destroy).
- Vérifier après destroy qu'il ne reste rien : `aws s3 ls`,
  `aws lambda list-functions`, `aws events list-rules`.
