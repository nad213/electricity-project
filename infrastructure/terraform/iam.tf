# --------------------------------------------
# Common IAM Role for Lambdas (csv_to_sqs and 01_downloader)
# --------------------------------------------
resource "aws_iam_role" "lambda_common_role" {
  name = "lambda_common_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# --------------------------------------------
# Common IAM Policy for SQS and S3
# --------------------------------------------
resource "aws_iam_policy" "lambda_common_policy" {
  name        = "lambda_common_policy"
  description = "Allows Lambdas to interact with SQS and S3 for the download workflow"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # SQS Permissions (send, receive, delete messages, and read queue attributes)
      {
        Effect = "Allow",
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ],
        Resource = aws_sqs_queue.download_queue.arn
      },
      # S3 Permissions (read source files and logs)
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:HeadObject"
        ],
        Resource = [
          "${aws_s3_bucket.elecshiny_bucket.arn}/99_params/filelist.csv",
          "${aws_s3_bucket.elecshiny_bucket.arn}/01_downloaded/*",
          "${aws_s3_bucket.elecshiny_bucket.arn}/logs/*"
        ]

      },
      # S3 Permissions (write downloaded files, clean data, and logs)
      {
        Effect = "Allow",
        Action = [
          "s3:PutObject"
        ],
        Resource = [
          "${aws_s3_bucket.elecshiny_bucket.arn}/99_params/filelist.csv",
          "${aws_s3_bucket.elecshiny_bucket.arn}/01_downloaded/*",
          "${aws_s3_bucket.elecshiny_bucket.arn}/02_clean/*",
          "${aws_s3_bucket.elecshiny_bucket.arn}/logs/*"
        ]
      },
      # CloudWatch Logs Permissions (required for Lambda)
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*"
      }
    ]
  })
}

# --------------------------------------------
# Attach the policy to the common role
# --------------------------------------------
resource "aws_iam_role_policy_attachment" "lambda_common_attach" {
  role       = aws_iam_role.lambda_common_role.name
  policy_arn = aws_iam_policy.lambda_common_policy.arn
}

# --------------------------------------------
# Lambda Permission: Allow EventBridge to invoke csv_to_sqs
# --------------------------------------------
resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.csv_to_sqs.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger.arn
}


# --------------------------------------------
# Lambda Permission: Allow EventBridge to invoke transform_conso_france
# --------------------------------------------
resource "aws_lambda_permission" "allow_cloudwatch_transform" {
  statement_id  = "AllowExecutionFromCloudWatchTransform"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.transform_conso_france.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger_transform.arn
}

# --------------------------------------------
# Lambda Permission: Allow EventBridge to invoke transform_production_france
# --------------------------------------------
resource "aws_lambda_permission" "allow_cloudwatch_transform_production" {
  statement_id  = "AllowExecutionFromCloudWatchTransformProduction"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.transform_production_france.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger_transform_production.arn
}

# --------------------------------------------
# Lambda Permission: Allow EventBridge to invoke transform_echanges_france
# --------------------------------------------
resource "aws_lambda_permission" "allow_cloudwatch_transform_echanges" {
  statement_id  = "AllowExecutionFromCloudWatchTransformEchanges"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.transform_echanges_france.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger_transform_echanges.arn
}