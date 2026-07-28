# Stack ETL Scaleway — déployé par le workflow CI infra-deploy.yml (push master
# sur infrastructure/**) ; apply manuel possible depuis ce dossier après
# `bash package_functions.sh`.
#
# Auth provider : SCW_ACCESS_KEY, SCW_SECRET_KEY, SCW_DEFAULT_PROJECT_ID,
#                 SCW_DEFAULT_ORGANIZATION_ID (env vars, pas de creds dans le code).
# Auth backend  : AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (le backend s3 ne lit
#                 pas les TF_VAR_*) — exporter les valeurs de TF_VAR_s3_* avant
#                 init/plan/apply :
#                 export AWS_ACCESS_KEY_ID="$TF_VAR_s3_access_key"
#                 export AWS_SECRET_ACCESS_KEY="$TF_VAR_s3_secret_key"

terraform {
  required_providers {
    scaleway = {
      source = "scaleway/scaleway"
    }
  }

  # State distant sur Object Storage Scaleway (bucket dédié versionné, créé hors
  # Terraform pour éviter le chicken-and-egg ; pas de lock — ne pas lancer
  # d'apply local pendant qu'un run CI tourne).
  backend "s3" {
    bucket = "elec-tfstate-scw"
    key    = "terraform-scaleway/terraform.tfstate"
    region = "fr-par"
    endpoints = {
      s3 = "https://s3.fr-par.scw.cloud"
    }
    # Backend AWS utilisé hors AWS : ne pas valider comptes/régions AWS,
    # et Scaleway ne supporte pas les checksums S3 récents.
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
  }
}

variable "region" {
  type    = string
  default = "fr-par"
}

provider "scaleway" {
  region = var.region
  zone   = "${var.region}-1"
}

resource "scaleway_object_bucket" "elec" {
  name = var.bucket_name
}

variable "bucket_name" {
  type    = string
  default = "elec-app-scw"
}

# Creds S3 injectés dans les functions (boto3 les lit nativement via AWS_*)
variable "s3_access_key" {
  type      = string
  sensitive = true
}

variable "s3_secret_key" {
  type      = string
  sensitive = true
}
