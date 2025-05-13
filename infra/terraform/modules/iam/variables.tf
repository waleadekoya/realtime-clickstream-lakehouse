variable "project" {
  type        = string
  description = "Project name prefix"
}

variable "environment" {
  type        = string
  description = "Deployment environment (dev, staging, prod)"
}

variable "stream_arn" {
  type        = string
  description = "ARN of the Kinesis stream"
}

variable "bucket_arn" {
  type        = string
  description = "ARN of the S3 bucket"
}

variable "region" {
  type        = string
  description = "AWS region"
}

