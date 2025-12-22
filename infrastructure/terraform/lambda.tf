#################################################
# 00. CSV TO SQS LAMBDA (00_csv_to_sqs)
#################################################
# 00.1 Lambda Function: 00_csv_to_sqs
# --------------------------------------------
resource "aws_lambda_function" "csv_to_sqs" {
  filename         = "../lambdas/00_csv_to_sqs/csv_to_sqs.zip"
  function_name    = "00_csv_to_sqs"
  role             = aws_iam_role.lambda_common_role.arn
  handler          = "csv_to_sqs.lambda_handler"
  runtime          = "python3.9"
  timeout          = 60
  memory_size      = 128
  source_code_hash = filebase64sha256("../lambdas/00_csv_to_sqs/csv_to_sqs.zip")
  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.elecshiny_bucket.bucket
      QUEUE_URL   = aws_sqs_queue.download_queue.url
    }
  }
}

#################################################
# 01. DOWNLOADER LAMBDA (01_downloader)
#################################################
# 01.1 Lambda Function: 01_downloader
# --------------------------------------------
resource "aws_lambda_function" "downloader" {
  filename         = "../lambdas/01_download/download.zip"
  function_name    = "01_downloader"
  role             = aws_iam_role.lambda_common_role.arn
  handler          = "download.lambda_handler"
  runtime          = "python3.9"
  timeout          = 300
  memory_size      = 256
  source_code_hash = filebase64sha256("../lambdas/01_download/download.zip")
  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.elecshiny_bucket.bucket
      QUEUE_URL   = aws_sqs_queue.download_queue.url
    }
  }
}

#################################################
# 02. TRANSFORM CONSO-FRANCE LAMBDA (02_transform_conso-france)
#################################################
# 02.1 Lambda Function: 02_transform_conso_france
# --------------------------------------------
resource "aws_lambda_function" "transform_conso_france" {
    layers = [
    "arn:aws:lambda:eu-west-3:336392948345:layer:AWSSDKPandas-Python39:33"
  ]
  filename         = "../lambdas/02_transform/transform_conso_france.zip"
  source_code_hash = filebase64sha256("../lambdas/02_transform/transform_conso_france.zip")
  function_name    = "02_transform_conso_france"
  role             = aws_iam_role.lambda_common_role.arn
  handler          = "transform_conso_france.lambda_handler"
  runtime          = "python3.9"
  timeout          = 300
  memory_size      = 2048
  #source_code_hash = filebase64sha256("lambda/02_transform/transform_conso_france.zip")

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.elecshiny_bucket.bucket
    }
  }
}

#################################################
# 02. TRANSFORM PRODUCTION-FRANCE LAMBDA (02_transform_production-france)
#################################################
# 02.2 Lambda Function: 02_transform_production_france
# --------------------------------------------
resource "aws_lambda_function" "transform_production_france" {
  layers = [
    "arn:aws:lambda:eu-west-3:336392948345:layer:AWSSDKPandas-Python39:33"
  ]
  filename         = "../lambdas/02_transform/transform_production_france.zip"
  source_code_hash = filebase64sha256("../lambdas/02_transform/transform_production_france.zip")
  function_name    = "02_transform_production_france"
  role             = aws_iam_role.lambda_common_role.arn
  handler          = "transform_production_france.lambda_handler"
  runtime          = "python3.9"
  timeout          = 300
  memory_size      = 2048

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.elecshiny_bucket.bucket
    }
  }
}



# --------------------------------------------
# Event Source Mapping: SQS -> Downloader Lambda
# --------------------------------------------
# Triggers the "downloader" Lambda for each new message in the SQS queue.
# batch_size = 1: Only one message is processed at a time to avoid conflicts.
# --------------------------------------------
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.download_queue.arn
  function_name    = aws_lambda_function.downloader.arn
  batch_size       = 1
  enabled          = true
}

#################################################
# 00.9 CloudWatch Event Rule: Daily Trigger
#################################################
# Creates a CloudWatch Event Rule to trigger an event on a cron schedule.
# This rule is set to trigger daily at 07:00 UTC.
# Cron format: "cron(minutes hours day_of_month month day_of_week year)"
# "*" means "all possible values" for that field.
#################################################
resource "aws_cloudwatch_event_rule" "daily_trigger" {
  name                = "trigger-csv-to-sqs-daily"  
  schedule_expression = "cron(0 6 * * ? *)"        # Daily at 07:00 UTC
}

#################################################
# 00.10 CloudWatch Event Target: Rule Target
#################################################
# Associates the above CloudWatch rule with the "csv_to_sqs" Lambda function.
# This means the Lambda will be invoked automatically according to the schedule.
# - rule      : Reference to the CloudWatch rule defined above.
# - target_id : Unique identifier for this target.
# - arn       : ARN of the Lambda function to be triggered.
#################################################
resource "aws_cloudwatch_event_target" "trigger_csv_to_sqs" {
  rule      = aws_cloudwatch_event_rule.daily_trigger.name  
  target_id = "csv_to_sqs"                                  
  arn       = aws_lambda_function.csv_to_sqs.arn             
}

#################################################
# CloudWatch Event Rule: Daily Trigger for transform_conso_france
#################################################
resource "aws_cloudwatch_event_rule" "daily_trigger_transform" {
  name                = "trigger-transform-conso-france-daily"
  schedule_expression = "cron(0 7 * * ? *)"  # 7h UTC = 8h UTC+1 ou 9h UTC+2
}

#################################################
# CloudWatch Event Target: Rule Target for transform_conso_france
#################################################
resource "aws_cloudwatch_event_target" "trigger_transform_conso_france" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_transform.name
  target_id = "transform_conso_france"
  arn       = aws_lambda_function.transform_conso_france.arn
}

#################################################
# CloudWatch Event Rule: Daily Trigger for transform_production_france
#################################################
resource "aws_cloudwatch_event_rule" "daily_trigger_transform_production" {
  name                = "trigger-transform-production-france-daily"
  schedule_expression = "cron(0 7 * * ? *)"  # 7h UTC = 8h UTC+1 ou 9h UTC+2
}

#################################################
# CloudWatch Event Target: Rule Target for transform_production_france
#################################################
resource "aws_cloudwatch_event_target" "trigger_transform_production_france" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_transform_production.name
  target_id = "transform_production_france"
  arn       = aws_lambda_function.transform_production_france.arn
}
