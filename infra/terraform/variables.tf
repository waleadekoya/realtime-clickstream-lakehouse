variable "project" {
  type    = string
  default = "clickstream-lakehouse"
}
variable "environment" {
  type        = string
  description = "Deployment target: dev, staging, prod"
  default     = "dev"
}

variable "aws_region" {
  type    = string
  description = "AWS region to deploy resources"
  default = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "CIDR block for the subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "availability_zone" {
  description = "Availability zone for the subnet"
  type        = string
  default     = "us-east-1a"
}

variable "python_command" {
  description = "Python command to use for local-exec provisioner"
  type        = string
  default     = "python"
}
