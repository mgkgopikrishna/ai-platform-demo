variable "name" {
  description = "Service name, e.g. team-a-api."
  type        = string
}

variable "vpc_id" {
  description = "VPC to deploy into (from the network module)."
  type        = string
}

variable "public_subnet_ids" {
  description = "Subnets for the load balancer."
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Subnets for the Fargate tasks."
  type        = list(string)
}

variable "container_image" {
  description = "Full image URI including an immutable tag or digest (never :latest)."
  type        = string

  validation {
    condition     = !endswith(var.container_image, ":latest")
    error_message = "Use an immutable tag or digest; ':latest' breaks reproducible deploys and rollbacks."
  }
}

variable "container_port" {
  description = "Port the container listens on."
  type        = number
  default     = 8080
}

variable "health_check_path" {
  description = "HTTP path the load balancer uses to decide if a task is healthy."
  type        = string
  default     = "/healthz"
}

variable "cpu" {
  description = "Task CPU units (256 = 0.25 vCPU)."
  type        = number
  default     = 256
}

variable "memory" {
  description = "Task memory in MiB."
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Baseline number of tasks."
  type        = number
  default     = 2
}

variable "min_count" {
  description = "Autoscaling floor."
  type        = number
  default     = 2
}

variable "max_count" {
  description = "Autoscaling ceiling."
  type        = number
  default     = 6
}

variable "cpu_target_percent" {
  description = "Target average CPU for autoscaling."
  type        = number
  default     = 60
}

variable "environment" {
  description = "Plain (non-secret) environment variables for the container."
  type        = map(string)
  default     = {}
}

variable "certificate_arn" {
  description = "ACM certificate ARN. When set, the ALB serves HTTPS and redirects HTTP to HTTPS."
  type        = string
  default     = null
}

variable "deletion_protection" {
  description = "Prevent accidental deletion of the load balancer. Turn on for prod."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention."
  type        = number
  default     = 30
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic for alarms (wire to PagerDuty/Slack). Null disables notifications."
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
