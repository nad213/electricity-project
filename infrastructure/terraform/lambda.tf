#################################################
# 01. ODRE ECO2MIX LAMBDA (download + transform)
#################################################
resource "aws_lambda_function" "odre_eco2mix" {
  layers = [
    "arn:aws:lambda:eu-west-3:336392948345:layer:AWSSDKPandas-Python312:13"
  ]
  filename         = "../lambdas/01_odre_eco2mix/odre_eco2mix.zip"
  source_code_hash = filebase64sha256("../lambdas/01_odre_eco2mix/odre_eco2mix.zip")
  function_name    = "01_odre_eco2mix"
  role             = aws_iam_role.lambda_common_role.arn
  handler          = "odre_eco2mix.lambda_handler"
  runtime          = "python3.12"
  timeout          = 300
  memory_size      = 2048

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.elecshiny_bucket.bucket
    }
  }
}

# Declenchement horaire. La lambda vérifie `data_processed` et ne re-télécharge/re-transforme
# que si la source a bougé, donc les runs sans nouveauté sont des no-op (2 GET métadonnées + early-return).
#
# Bascule Scaleway (plans/migration-etl-scaleway.md, étape 5.2) : crons AWS coupés
# le 2026-07-08 (state = "DISABLED" sur les 3 rules), pipeline repris par les crons
# Scaleway Functions. Tout changement d'état doit passer par ICI puis merge sur
# master (le workflow infra-deploy applique) — un toggle console serait écrasé au
# prochain apply CI.
resource "aws_cloudwatch_event_rule" "live_trigger_odre" {
  name                = "trigger-odre-eco2mix-hourly"
  schedule_expression = "rate(1 hour)"
  state               = "DISABLED" # coupé le 2026-07-08 — pipeline migré sur Scaleway Functions
}

resource "aws_cloudwatch_event_target" "trigger_odre_live" {
  rule      = aws_cloudwatch_event_rule.live_trigger_odre.name
  target_id = "odre_eco2mix"
  arn       = aws_lambda_function.odre_eco2mix.arn
}


#################################################
# 02. SCRAPE RTE PRODUCTION LAMBDA
#################################################
resource "aws_lambda_function" "scrape_rte_production" {
  layers = [
    "arn:aws:lambda:eu-west-3:336392948345:layer:AWSSDKPandas-Python312:13"
  ]
  filename         = "../lambdas/02_scrape_rte_production/scrape_rte_production.zip"
  source_code_hash = filebase64sha256("../lambdas/02_scrape_rte_production/scrape_rte_production.zip")
  function_name    = "02_scrape_rte_production"
  role             = aws_iam_role.lambda_common_role.arn
  handler          = "scrape_rte_production.lambda_handler"
  runtime          = "python3.12"
  timeout          = 120
  memory_size      = 512

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.elecshiny_bucket.bucket
    }
  }
}

resource "aws_cloudwatch_event_rule" "daily_trigger_rte_production" {
  name                = "trigger-scrape-rte-production-daily"
  schedule_expression = "cron(0 7 * * ? *)" # Daily at 07:00 UTC
  state               = "DISABLED"          # coupé le 2026-07-08 — pipeline migré sur Scaleway Functions
}

resource "aws_cloudwatch_event_target" "trigger_scrape_rte_production" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_rte_production.name
  target_id = "scrape_rte_production"
  arn       = aws_lambda_function.scrape_rte_production.arn
}


#################################################
# 03. RTE PMAX LAMBDA
#################################################
resource "aws_lambda_function" "rte_pmax" {
  layers = [
    "arn:aws:lambda:eu-west-3:336392948345:layer:AWSSDKPandas-Python312:13"
  ]
  filename         = "../lambdas/03_rte_pmax/rte_pmax.zip"
  source_code_hash = filebase64sha256("../lambdas/03_rte_pmax/rte_pmax.zip")
  function_name    = "03_rte_pmax"
  role             = aws_iam_role.lambda_common_role.arn
  handler          = "rte_pmax.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.elecshiny_bucket.bucket
    }
  }
}

resource "aws_cloudwatch_event_rule" "daily_trigger_rte_pmax" {
  name                = "trigger-rte-pmax-daily"
  schedule_expression = "cron(5 7 * * ? *)" # Daily at 07:05 UTC
  state               = "DISABLED"          # coupé le 2026-07-08 — pipeline migré sur Scaleway Functions
}

resource "aws_cloudwatch_event_target" "trigger_rte_pmax" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_rte_pmax.name
  target_id = "rte_pmax"
  arn       = aws_lambda_function.rte_pmax.arn
}
