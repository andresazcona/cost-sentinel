variable "aws_region" {
  description = "Region the Lambda runs in. It can scan other regions."
  type        = string
  default     = "us-east-1"
}

variable "regions" {
  description = "Regions to scan."
  type        = list(string)
  default     = ["us-east-1"]

  validation {
    condition     = length(var.regions) > 0
    error_message = "Scan at least one region."
  }
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression. Default: Mondays 08:00."
  type        = string
  default     = "cron(0 8 ? * MON *)"
}

variable "schedule_timezone" {
  type    = string
  default = "UTC"
}

variable "required_tags" {
  description = "Tag keys every resource must carry. Empty list disables the check."
  type        = list(string)
  default     = ["owner", "cost-center"]
}

variable "snapshot_max_age_days" {
  type    = number
  default = 90
}

variable "stopped_max_days" {
  type    = number
  default = 30
}

variable "ami_max_age_days" {
  type    = number
  default = 180
}

variable "check_amis" {
  description = "Report self-owned AMIs older than ami_max_age_days that no instance uses."
  type        = bool
  default     = false
}

variable "dry_run" {
  description = "When true, remediation only logs what it would do."
  type        = bool
  default     = true
}

variable "enable_remediation" {
  description = "Attach the write policy. Without it remediate_checks is ignored."
  type        = bool
  default     = false
}

variable "remediate_checks" {
  description = "Checks allowed to clean up after themselves."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for c in var.remediate_checks :
      contains(["unattached_volume", "unassociated_eip", "old_snapshot", "old_ami"], c)
    ])
    error_message = "Only unattached_volume, unassociated_eip, old_snapshot and old_ami support remediation."
  }
}

variable "ses_sender" {
  description = "Verified SES identity used as From. Empty disables email."
  type        = string
  default     = ""
}

variable "ses_recipients" {
  type    = list(string)
  default = []
}

variable "slack_webhook_parameter" {
  description = "Name of an SSM SecureString holding the Slack webhook URL, created out of band. Empty disables Slack."
  type        = string
  default     = ""

  validation {
    condition     = var.slack_webhook_parameter == "" || startswith(var.slack_webhook_parameter, "/")
    error_message = "Use a hierarchical parameter name such as /cost-sentinel/slack-webhook."
  }
}

variable "alarm_topic_arn" {
  description = "Optional SNS topic notified when a run fails and lands in the DLQ."
  type        = string
  default     = null
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "tags" {
  description = "Extra tags for every resource created here."
  type        = map(string)
  default     = {}
}
