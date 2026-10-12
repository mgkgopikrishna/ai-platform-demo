variable "name" {
  description = "Name prefix for all network resources (usually <team>-<env>)."
  type        = string
}

variable "cidr_block" {
  description = "VPC CIDR block."
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3 for high availability."
  }
}

variable "single_nat_gateway" {
  description = "Use one shared NAT gateway (cheaper, for non-prod) instead of one per AZ."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
