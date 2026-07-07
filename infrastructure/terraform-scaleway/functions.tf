# 3 Serverless Functions = les 3 lambdas AWS, même code, même signature
# lambda_handler(event, context). Zips produits par package_functions.sh
# (deps vendorées dans package/ — pas de layers chez Scaleway).
#
# Mémoire : provisionné AWS conservé pour eco2mix (pic mesuré 1010 Mo le
# 2026-07-07, croît avec l'historique) ; 512/256 pour les deux autres.

locals {
  common_env = {
    BUCKET_NAME     = scaleway_object_bucket.elec.name
    S3_ENDPOINT_URL = "https://s3.fr-par.scw.cloud"
    AWS_DEFAULT_REGION = "fr-par"
  }
  common_secrets = {
    AWS_ACCESS_KEY_ID     = var.s3_access_key
    AWS_SECRET_ACCESS_KEY = var.s3_secret_key
  }
}

resource "scaleway_function_namespace" "etl" {
  name        = "elec-etl"
  description = "Pipeline ETL ElecStat (ex-lambdas AWS)"
}

#################################################
# 01. ODRE ECO2MIX (download + transform, horaire)
#################################################
resource "scaleway_function" "odre_eco2mix" {
  namespace_id = scaleway_function_namespace.etl.id
  name         = "odre-eco2mix"
  runtime      = "python312"
  handler      = "odre_eco2mix.lambda_handler"
  memory_limit = 2048
  timeout      = 300
  privacy      = "private"
  deploy       = true
  zip_file     = "build/odre_eco2mix.zip"
  zip_hash     = filesha256("build/odre_eco2mix.zip")
  max_scale    = 1

  environment_variables        = local.common_env
  secret_environment_variables = local.common_secrets
}

resource "scaleway_function_cron" "odre_hourly" {
  function_id = scaleway_function.odre_eco2mix.id
  schedule    = "0 * * * *"
  args        = jsonencode({})
}

#################################################
# 02. SCRAPE RTE PRODUCTION (quotidien 07:00 UTC)
#################################################
resource "scaleway_function" "scrape_rte_production" {
  namespace_id = scaleway_function_namespace.etl.id
  name         = "scrape-rte-production"
  runtime      = "python312"
  handler      = "scrape_rte_production.lambda_handler"
  memory_limit = 512
  timeout      = 120
  privacy      = "private"
  deploy       = true
  zip_file     = "build/scrape_rte_production.zip"
  zip_hash     = filesha256("build/scrape_rte_production.zip")
  max_scale    = 1

  environment_variables        = local.common_env
  secret_environment_variables = local.common_secrets
}

resource "scaleway_function_cron" "scrape_rte_daily" {
  function_id = scaleway_function.scrape_rte_production.id
  schedule    = "0 7 * * *"
  args        = jsonencode({})
}

#################################################
# 03. RTE PMAX (quotidien 07:05 UTC)
#################################################
resource "scaleway_function" "rte_pmax" {
  namespace_id = scaleway_function_namespace.etl.id
  name         = "rte-pmax"
  runtime      = "python312"
  handler      = "rte_pmax.lambda_handler"
  memory_limit = 256
  timeout      = 60
  privacy      = "private"
  deploy       = true
  zip_file     = "build/rte_pmax.zip"
  zip_hash     = filesha256("build/rte_pmax.zip")
  max_scale    = 1

  environment_variables        = local.common_env
  secret_environment_variables = local.common_secrets
}

resource "scaleway_function_cron" "pmax_daily" {
  function_id = scaleway_function.rte_pmax.id
  schedule    = "5 7 * * *"
  args        = jsonencode({})
}
