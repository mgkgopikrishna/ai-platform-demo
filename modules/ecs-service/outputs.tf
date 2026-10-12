output "service_url" {
  description = "Public URL of the service."
  value       = "${local.https_enabled ? "https" : "http"}://${aws_lb.this.dns_name}"
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.this.name
}

output "task_role_name" {
  description = "Application IAM role; attach least-privilege policies here."
  value       = aws_iam_role.task.name
}

output "log_group_name" {
  description = "CloudWatch log group for the service."
  value       = aws_cloudwatch_log_group.this.name
}
