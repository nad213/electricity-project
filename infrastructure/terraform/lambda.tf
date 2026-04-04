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
# 02. TRANSFORM ODRE ECO2MIX LAMBDA (02_transform_odre_eco2mix)
#################################################
resource "aws_lambda_function" "transform_odre_eco2mix" {
  layers = [
    "arn:aws:lambda:eu-west-3:336392948345:layer:AWSSDKPandas-Python39:33"
  ]
  filename         = "../lambdas/02_transform_odre_eco2mix/transform_odre_eco2mix.zip"
  source_code_hash = filebase64sha256("../lambdas/02_transform_odre_eco2mix/transform_odre_eco2mix.zip")
  function_name    = "02_transform_odre_eco2mix"
  role             = aws_iam_role.lambda_common_role.arn
  handler          = "transform_odre_eco2mix.lambda_handler"
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
# 00.9 CloudWatch Event Rules: csv_to_sqs Triggers
#################################################
# 3 separate rules because each trigger uses different minutes.
# Cron format: "cron(minutes hours day_of_month month day_of_week year)"
#################################################
resource "aws_cloudwatch_event_rule" "daily_trigger_1" {
  name                = "trigger-csv-to-sqs-0607"
  schedule_expression = "cron(7 6 * * ? *)" # 06:07 UTC
}

resource "aws_cloudwatch_event_rule" "daily_trigger_2" {
  name                = "trigger-csv-to-sqs-1219"
  schedule_expression = "cron(19 12 * * ? *)" # 12:19 UTC
}

resource "aws_cloudwatch_event_rule" "daily_trigger_3" {
  name                = "trigger-csv-to-sqs-1810"
  schedule_expression = "cron(10 18 * * ? *)" # 18:10 UTC
}

#################################################
# 00.10 CloudWatch Event Targets: csv_to_sqs
#################################################
resource "aws_cloudwatch_event_target" "trigger_csv_to_sqs_1" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_1.name
  target_id = "csv_to_sqs"
  arn       = aws_lambda_function.csv_to_sqs.arn
}

resource "aws_cloudwatch_event_target" "trigger_csv_to_sqs_2" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_2.name
  target_id = "csv_to_sqs"
  arn       = aws_lambda_function.csv_to_sqs.arn
}

resource "aws_cloudwatch_event_target" "trigger_csv_to_sqs_3" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_3.name
  target_id = "csv_to_sqs"
  arn       = aws_lambda_function.csv_to_sqs.arn
}

#################################################
# CloudWatch Event Rule: Daily Trigger for transform_odre_eco2mix
#################################################
resource "aws_cloudwatch_event_rule" "daily_trigger_transform" {
  name                = "trigger-transform-all-daily"
  schedule_expression = "cron(0 7,13,19 * * ? *)" # 3x daily at 07:00, 13:00, 19:00 UTC
}

#################################################
# CloudWatch Event Target: Rule Target for transform_odre_eco2mix
#################################################
resource "aws_cloudwatch_event_target" "trigger_transform_odre_eco2mix" {
  rule      = aws_cloudwatch_event_rule.daily_trigger_transform.name
  target_id = "transform_odre_eco2mix"
  arn       = aws_lambda_function.transform_odre_eco2mix.arn
}
