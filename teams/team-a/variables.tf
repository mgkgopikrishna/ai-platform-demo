variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}

variable "container_image" {
  description = "Immutable image URI for the team-a API."
  type        = string
  default     = "public.ecr.aws/nginx/nginx:1.27"
}

variable "certificate_arn" {
  description = "ACM certificate for HTTPS. Null serves HTTP only (dev)."
  type        = string
  default     = null
}
