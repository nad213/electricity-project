# 3 Serverless Functions — point d'entrée commun : <nom>.lambda_handler(event, context).
#
# ⚠️ PRÉREQUIS avant tout plan/apply : `bash package_functions.sh` — les zips
# build/*.zip sont gitignorés, filesha256() échoue en dur s'ils sont absents.
# NB : les zips ne sont pas reproductibles (mtimes) → chaque repackage change
# zip_hash et redéploie les 3 functions, même à code identique. Sans gravité
# (max_scale=1), mais ne repackager que quand c'est nécessaire.
#
# Mémoire : 2048 Mo pour eco2mix (pic mesuré 1010 Mo, croît avec l'historique) ;
# 512/256 pour les deux autres.

locals {
  common_env = {
    BUCKET_NAME        = scaleway_object_bucket.elec.name
    S3_ENDPOINT_URL    = "https://s3.${var.region}.scw.cloud"
    AWS_DEFAULT_REGION = var.region
  }
  common_secrets = {
    AWS_ACCESS_KEY_ID     = var.s3_access_key
    AWS_SECRET_ACCESS_KEY = var.s3_secret_key
  }

  # Clé = nom du handler (fichier .py et zip) ; name Scaleway dérivé (tirets).
  functions = {
    odre_eco2mix = { # download + transform ODRE, horaire
      memory_limit = 2048
      timeout      = 300
      schedule     = "0 * * * *"
    }
    scrape_rte_production = { # scraping RTE, quotidien 07:00 UTC
      memory_limit = 512
      timeout      = 120
      schedule     = "0 7 * * *"
    }
    rte_pmax = { # snapshot puissance installée, quotidien 07:05 UTC
      memory_limit = 256
      timeout      = 60
      schedule     = "5 7 * * *"
    }
  }
}

resource "scaleway_function_namespace" "etl" {
  name        = "elec-etl"
  description = "Pipeline ETL ElecStat"
}

resource "scaleway_function" "etl" {
  for_each = local.functions

  namespace_id = scaleway_function_namespace.etl.id
  name         = replace(each.key, "_", "-")
  runtime      = "python312"
  handler      = "${each.key}.lambda_handler"
  memory_limit = each.value.memory_limit
  timeout      = each.value.timeout
  privacy      = "private"
  deploy       = true
  # zip_file sans path.module : "./build/…" créerait un faux diff avec le state
  # (apply toujours lancé depuis ce dossier, où path.module = ".")
  zip_file     = "build/${each.key}.zip"
  zip_hash     = filesha256("${path.module}/build/${each.key}.zip")
  max_scale    = 1

  environment_variables        = local.common_env
  secret_environment_variables = local.common_secrets
}

resource "scaleway_function_cron" "etl" {
  for_each = local.functions

  function_id = scaleway_function.etl[each.key].id
  schedule    = each.value.schedule
  args        = jsonencode({})
}

# Les ressources ont été créées nommées individuellement, avant la factorisation
# for_each — ces blocs moved évitent un destroy/recreate des functions live.
moved {
  from = scaleway_function.odre_eco2mix
  to   = scaleway_function.etl["odre_eco2mix"]
}

moved {
  from = scaleway_function.scrape_rte_production
  to   = scaleway_function.etl["scrape_rte_production"]
}

moved {
  from = scaleway_function.rte_pmax
  to   = scaleway_function.etl["rte_pmax"]
}

moved {
  from = scaleway_function_cron.odre_hourly
  to   = scaleway_function_cron.etl["odre_eco2mix"]
}

moved {
  from = scaleway_function_cron.scrape_rte_daily
  to   = scaleway_function_cron.etl["scrape_rte_production"]
}

moved {
  from = scaleway_function_cron.pmax_daily
  to   = scaleway_function_cron.etl["rte_pmax"]
}
