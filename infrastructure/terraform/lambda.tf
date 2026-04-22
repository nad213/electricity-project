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

resource "aws_cloudwatch_event_rule" "daily_trigger_odre_1" {
  name                = "trigger-odre-eco2mix-0607"
  schedule_expression = "cron(7 6 * * ? *)" # 06:07 UTC
}

resource "aws_cloudwatch_event_rule" "daily_trigger_odre_2" {
  name                = "trigger-odre-eco2mix-1219"
  schedule_expression = "cron(19 12 * * ? *)" # 12:19 UTC
}

resource "aws_cloudwatch_event_rule" "daily_trigger_odre_3" {
  name                = "trigger-odre-eco2mix-1810"
  schedule_expression = "cron(10 18 * * ? *)" # 18:10 UTC
}

resource "aws_cloudwatch_event_target" "trigger_odre_1" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_odre_1.name
  target_id = "odre_eco2mix"
  arn       = aws_lambda_function.odre_eco2mix.arn
}

resource "aws_cloudwatch_event_target" "trigger_odre_2" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_odre_2.name
  target_id = "odre_eco2mix"
  arn       = aws_lambda_function.odre_eco2mix.arn
}

resource "aws_cloudwatch_event_target" "trigger_odre_3" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_odre_3.name
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
}

resource "aws_cloudwatch_event_target" "trigger_rte_pmax" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_rte_pmax.name
  target_id = "rte_pmax"
  arn       = aws_lambda_function.rte_pmax.arn
}
