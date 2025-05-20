variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
}


variable "lambda_layer_s3_bucket" {
  description = "S3 bucket where the Lambda Layer ZIP is stored"
  type        = string
}

variable "lambda_layer_s3_key" {
  description = "S3 key for the Lambda Layer ZIP"
  type        = string
}

variable "lambda_layer_local_path" {
  description = "Local path to the Lambda Layer ZIP file"
  type        = string
}
