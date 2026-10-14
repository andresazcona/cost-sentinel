output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "dead_letter_queue_url" {
  value = aws_sqs_queue.dlq.url
}

output "remediation_enabled" {
  value = var.enable_remediation && !var.dry_run && length(var.remediate_checks) > 0
}
