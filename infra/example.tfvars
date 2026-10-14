regions        = ["us-east-1", "eu-west-1"]
required_tags  = ["owner", "cost-center"]
ses_sender     = "finops@example.com"
ses_recipients = ["platform-team@example.com"]

# Created out of band so the webhook never enters Terraform state:
#   aws ssm put-parameter --name /cost-sentinel/slack-webhook --type SecureString --value https://hooks.slack.com/...
slack_webhook_parameter = "/cost-sentinel/slack-webhook"

# Start report-only. Flip these after a few weeks of reading the reports.
dry_run            = true
enable_remediation = false
remediate_checks   = ["unassociated_eip", "unattached_volume"]

tags = { owner = "platform-team", cost-center = "cc-0000" }
