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

variable "delta_jar_source_path" {
  description = "Local filesystem path to Delta Lake core JAR"
  type        = string
  default = "libs/jars/delta-core_2.12-1.2.1.jar"
}

variable "schema_registry_source_path" {
  description = "Local filesystem path to AWS Glue Schema Registry client JAR"
  type        = string
  default     = "libs/jars/schema-registry-serde-1.1.23.jar"
}

variable "delta_jar_key" {
  description = "Filename/key for Delta Lake core JAR in S3"
  type        = string
  default     = "delta-core_2.12-1.2.1.jar"
}

variable "schema_registry_jar_key" {
  description = "Filename/key for AWS Glue Schema Registry client JAR in S3"
  type        = string
  default     = "schema-registry-serde-1.1.23.jar"
}

