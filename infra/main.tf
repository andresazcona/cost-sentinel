data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  name       = "cost-sentinel"
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  partition  = data.aws_partition.current.partition
}

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/build/${local.name}.zip"
  excludes    = ["cost_sentinel/__pycache__"]
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = var.log_retention_days
}

# Failed async invocations and failed schedule deliveries both land here.
resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_lambda_function" "this" {
  function_name    = local.name
  description      = "Weekly report of forgotten AWS resources and what they cost."
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "cost_sentinel.handler.lambda_handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  memory_size      = 256
  timeout          = 900 # snapshot-before-delete can wait up to 10 minutes

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  environment {
    variables = {
      REGIONS               = join(",", var.regions)
      REQUIRED_TAGS         = join(",", var.required_tags)
      SNAPSHOT_MAX_AGE_DAYS = tostring(var.snapshot_max_age_days)
      STOPPED_MAX_DAYS      = tostring(var.stopped_max_days)
      AMI_MAX_AGE_DAYS      = tostring(var.ami_max_age_days)
      CHECK_AMIS            = tostring(var.check_amis)
      DRY_RUN               = tostring(var.dry_run)
      REMEDIATE             = var.enable_remediation ? join(",", var.remediate_checks) : ""
      SES_SENDER            = var.ses_sender
      SES_RECIPIENTS        = join(",", var.ses_recipients)
      SLACK_WEBHOOK_PARAM   = var.slack_webhook_parameter
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# A retry would re-scan and send a duplicate report; failures go straight to the DLQ.
resource "aws_lambda_function_event_invoke_config" "this" {
  function_name          = aws_lambda_function.this.function_name
  maximum_retry_attempts = 0
}

resource "aws_scheduler_schedule" "weekly" {
  name                         = local.name
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.this.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts = 2
    }

    dead_letter_config {
      arn = aws_sqs_queue.dlq.arn
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "failed_runs" {
  alarm_name          = "${local.name}-failed-runs"
  alarm_description   = "A cost-sentinel run failed or could not be delivered. Inspect ${aws_sqs_queue.dlq.name}."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_topic_arn == null ? [] : [var.alarm_topic_arn]
}
