# Migration ETL AWS → Scaleway — voir plans/migration-etl-scaleway.md
# Coexiste avec infrastructure/terraform/ (AWS) jusqu'au démantèlement final.
#
# Auth : SCW_ACCESS_KEY, SCW_SECRET_KEY, SCW_DEFAULT_PROJECT_ID,
#        SCW_DEFAULT_ORGANIZATION_ID (env vars, pas de creds dans le code).

terraform {
  required_providers {
    scaleway = {
      source = "scaleway/scaleway"
    }
  }
  # Backend local pour démarrer ; bascule possible plus tard vers un backend s3
  # pointé sur Object Storage (endpoint https://s3.fr-par.scw.cloud).
}

provider "scaleway" {
  region = "fr-par"
  zone   = "fr-par-1"
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
