variable "aws_region" {
  description = "AWS region where resources will be created"
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "The GitHub repository in format: org-name/repo-name"
  type        = string
}
