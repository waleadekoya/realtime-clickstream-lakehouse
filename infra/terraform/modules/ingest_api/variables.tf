variable "project" {
  type        = string
  description = "Project name prefix"
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev, staging, prod)"
}

variable "region" {
  type        = string
  description = "AWS region"
}

variable "stream_arn" {
  type        = string
  description = "ARN of the Kinesis stream to receive click events"
}

variable "stream_name" {
  type        = string
  description = "Name of the Kinesis stream"
}

variable "code_s3_bucket" {
  type        = string
  description = "S3 bucket where Lambda ZIP will be uploaded"
}

variable "code_local_path" {
  type        = string
  description = "Local path to the Lambda ZIP (e.g. ../etl/handlers/click_handler.zip)"
}

variable "code_s3_key" {
  type        = string
  description = "Key under which to store the Lambda ZIP in S3"
}

variable "lambda_handler" {
  type        = string
  default     = "click_handler.lambda_handler"
  description = "Lambda handler"
}

variable "lambda_runtime" {
  type        = string
  default     = "python3.12"
  description = "Lambda runtime"
}

variable "lambda_timeout" {
  type        = number
  default     = 10
  description = "Lambda timeout in seconds"
}

variable "lambda_role_arn" {
  type        = string
  description = "ARN of the IAM role Lambda will assume"
}

variable "registry_name" {
  type        = string
  description = "Name of the Glue Schema registry"
}

variable "schema_name" {
    type        = string
    description = "Name of the Glue Schema"
}

variable "source_code_hash" {
  description = "Hash of the source code to detect changes"
  type        = string
  default     = null
}

variable "lambda_layers" {
  description = "List of Lambda layer ARNs to attach to the function"
  type        = list(string)
  default     = []
}

variable "python_command" {
  description = "Python command to use for local-exec provisioner"
  type        = string
  default     = "python"
}
