terraform {
  required_version = ">= 1.8.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }

  backend "s3" {
    bucket = "clickstream-tfstate" # create manually once
    key    = "state/terraform.tfstate"
    region = "us-east-1"

    # use_lockfile replaces the old dynamodb_table setting
    use_lockfile = true

  }
}

provider "aws" {
  region = var.aws_region
}
