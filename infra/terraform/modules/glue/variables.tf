
variable "project" {
  type        = string
  description = "Project name prefix"
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev, staging, prod)"
}

variable "role_arn" {
  type        = string
  description = "ARN of the IAM role for the Glue job"
}

variable "scripts_bucket" {
  type        = string
  description = "S3 bucket for Glue scripts"
}

variable "script_local_path" {
  type        = string
  description = "Local path to the Glue script"
}

variable "stream_name" {
  type        = string
  description = "Name of the Kinesis stream to process"
}

variable "stream_arn" {
  type        = string
  description = "The ARN of the Kinesis stream to process"
}

variable "region" {
  type        = string
  description = "AWS region"
}

variable "bronze_bucket_name" {
  type        = string
  description = "Name of the S3 bucket for bronze-layer data"
}

variable "connection_name" {
  description = "Name of the Glue connection"
  type        = string
}

variable "availability_zone" {
  description = "Availability zone for the Glue connection"
  type        = string
  default     = "us-east-1a"  # Or use a variable passed from parent module
}


variable "security_group_id" {
  description = "The ID of the security group to use for the Glue connection"
  type        = string
}

variable "subnet_id" {
  description = "The ID of the subnet to use for the Glue connection"
  type        = string
}

variable "default_arguments" {
  description = "Default arguments for the Glue job"
  type        = map(string)
  default     = {}
}

variable "delta_jar_source_path" {
  description = "Local path to the Delta Lake core JAR file"
  type        = string
}

variable "schema_registry_source_path" {
  description = "Local path to the AWS Glue Schema Registry client JAR file"
  type        = string
}

variable "delta_jar_key" {
  description = "S3 key under scripts_bucket for the Delta Lake core JAR"
  type        = string
  default     = "delta-core_2.12-1.2.1.jar"
}

variable "schema_registry_jar_key" {
  description = "Filename of the AWS Glue Schema Registry client JAR in libs/jars"
  type        = string
  default     = "schema-registry-serde-1.1.23.jar"
}

