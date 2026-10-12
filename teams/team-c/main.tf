# team-c: thin stack. All the platform logic lives in ../../modules.
# A team only declares *what* is different about its service.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Partial config; bucket/region/lock table are passed in by CI:
  #   terraform init -backend-config=../../backend.hcl -backend-config="key=team-c/terraform.tfstate"
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}

locals {
  name = "team-c-${var.environment}"
  tags = {
    team        = "team-c"
    environment = var.environment
    managed_by  = "terraform"
    repo        = "ai-platform-demo"
  }
}

module "network" {
  source = "../../modules/network"

  name               = local.name
  cidr_block         = "10.30.0.0/16"
  single_nat_gateway = var.environment != "prod"
  tags               = local.tags
}

module "api" {
  source = "../../modules/ecs-service"

  name                = "${local.name}-api"
  vpc_id              = module.network.vpc_id
  public_subnet_ids   = module.network.public_subnet_ids
  private_subnet_ids  = module.network.private_subnet_ids
  container_image     = var.container_image
  container_port      = 8000
  certificate_arn     = var.certificate_arn
  deletion_protection = var.environment == "prod"
  tags                = local.tags

  environment = {
    APP_ENV = var.environment
  }
}
