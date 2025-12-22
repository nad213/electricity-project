# --------------------------------------------
# SQS Queue for Download URLs
# --------------------------------------------
resource "aws_sqs_queue" "download_queue" {
  name                      = "elecshiny-download-queue"
  visibility_timeout_seconds = 360  
}
