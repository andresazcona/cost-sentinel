locals {
  destructive_actions = [
    "ec2:DeleteVolume",
    "ec2:ReleaseAddress",
    "ec2:DeleteSnapshot",
    "ec2:DeregisterImage",
  ]
}

# ---------- Lambda execution role: read-only by default ----------

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "read" {
  statement {
    sid = "DescribeOnly"
    actions = [
      "ec2:DescribeVolumes",
      "ec2:DescribeAddresses",
      "ec2:DescribeSnapshots",
      "ec2:DescribeImages",
      "ec2:DescribeInstances",
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeTargetHealth",
      "elasticloadbalancing:DescribeTags",
      "tag:GetResources",
    ]
    resources = ["*"] # Describe/List APIs do not support resource-level permissions
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = var.regions
    }
  }

  statement {
    sid       = "OwnLogsOnly"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid       = "DeadLetterQueue"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }

  dynamic "statement" {
    for_each = var.ses_sender == "" ? [] : [1]
    content {
      sid       = "SendReportFromConfiguredSenderOnly"
      actions   = ["ses:SendEmail"]
      resources = ["arn:${local.partition}:ses:${local.region}:${local.account_id}:identity/*"]
      condition {
        test     = "StringEquals"
        variable = "ses:FromAddress"
        values   = [var.ses_sender]
      }
    }
  }

  dynamic "statement" {
    for_each = var.slack_webhook_parameter == "" ? [] : [1]
    content {
      # The default aws/ssm key needs no kms:Decrypt grant; add one if you use a customer key.
      sid       = "ReadSlackWebhook"
      actions   = ["ssm:GetParameter"]
      resources = ["arn:${local.partition}:ssm:${local.region}:${local.account_id}:parameter${var.slack_webhook_parameter}"]
    }
  }
}

resource "aws_iam_role_policy" "read" {
  name   = "read-and-report"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.read.json
}

# ---------- Optional remediation policy ----------

data "aws_iam_policy_document" "remediate" {
  statement {
    sid       = "Remediate"
    actions   = concat(["ec2:CreateSnapshot"], local.destructive_actions)
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = var.regions
    }
  }

  statement {
    sid       = "TagBackupSnapshotsOnCreate"
    actions   = ["ec2:CreateTags"]
    resources = ["arn:${local.partition}:ec2:*::snapshot/*"]
    condition {
      test     = "StringEquals"
      variable = "ec2:CreateAction"
      values   = ["CreateSnapshot"]
    }
  }

  # The allowlist is enforced twice: in code, and here, so a bug cannot delete it.
  statement {
    sid       = "NeverTouchAllowlisted"
    effect    = "Deny"
    actions   = local.destructive_actions
    resources = ["*"]
    condition {
      test     = "StringEqualsIgnoreCase"
      variable = "aws:ResourceTag/cost-sentinel:ignore"
      values   = ["true"]
    }
  }
}

resource "aws_iam_role_policy" "remediate" {
  count  = var.enable_remediation ? 1 : 0
  name   = "remediate"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.remediate.json
}

# ---------- EventBridge Scheduler role ----------

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.this.arn]
  }
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "invoke-cost-sentinel"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}
