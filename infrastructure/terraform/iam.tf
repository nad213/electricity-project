# --------------------------------------------
# Common IAM Role for Lambdas
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
# Common IAM Policy for S3 and CloudWatch Logs
# --------------------------------------------
resource "aws_iam_policy" "lambda_common_policy" {
  name        = "lambda_common_policy"
  description = "Allows Lambdas to interact with S3 for the ETL pipeline"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # S3 Permissions (read source files and logs)
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:HeadObject"
        ],
        Resource = [
          "${aws_s3_bucket.elecshiny_bucket.arn}/01_downloaded/*",
          "${aws_s3_bucket.elecshiny_bucket.arn}/02_clean/*",
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
# Lambda Permissions: Allow EventBridge to invoke odre_eco2mix
# --------------------------------------------
resource "aws_lambda_permission" "allow_cloudwatch_odre_1" {
  statement_id  = "AllowExecutionFromCloudWatchOdre1"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.odre_eco2mix.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger_odre_1.arn
}

resource "aws_lambda_permission" "allow_cloudwatch_odre_2" {
  statement_id  = "AllowExecutionFromCloudWatchOdre2"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.odre_eco2mix.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger_odre_2.arn
}

resource "aws_lambda_permission" "allow_cloudwatch_odre_3" {
  statement_id  = "AllowExecutionFromCloudWatchOdre3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.odre_eco2mix.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger_odre_3.arn
}

# --------------------------------------------
# Lambda Permission: Allow EventBridge to invoke scrape_rte_production
# --------------------------------------------
resource "aws_lambda_permission" "allow_cloudwatch_scrape_rte_production" {
  statement_id  = "AllowExecutionFromCloudWatchScrapeRteProduction"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scrape_rte_production.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_trigger_rte_production.arn
}
