provider "aws" {
  region = var.aws_region
}

# GitHub OIDC Provider
resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# IAM Roles for GitHub Actions - one for each environment
locals {
  environments = ["dev", "staging", "prod"]
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "github_actions" {
  for_each = toset(local.environments)

  name = "${each.value}-GitHubActions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github_actions.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:*"
          }
        }
      }
    ]
  })

  tags = {
    Environment = each.value
    ManagedBy   = "terraform-oidc-setup"
  }
}

# IAM Policy for GitHub Actions to manage resources
resource "aws_iam_policy" "github_actions" {
  for_each = toset(local.environments)

  name        = "${each.value}-GitHubActionsPolicy"
  description = "Policy for GitHub Actions to deploy resources for ${each.value} environment"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          # S3 - for Terraform state
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",

          # DynamoDB - for Terraform state locking
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",

          # IAM permissions
          "iam:GetRole",
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:PutRolePolicy",
          "iam:GetRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:PassRole",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:ListAttachedRolePolicies",
          "iam:TagRole",

          # API Gateway
          "apigateway:*",

          # Lambda
          "lambda:*",

          # Kinesis
          "kinesis:*",

          # Glue
          "glue:*",

          # S3
          "s3:*",

          # CloudWatch
          "logs:*",

          # EC2 (for networking)
          "ec2:*",

          # VPC
          "vpc:*",

          # Step Functions
          "states:*",

          # Other permissions needed based on your modules
          "cloudformation:*",
          "kms:*",

          # IAM permissions
          "iam:ListRolePolicies",
          "iam:GetRolePolicy",
          "iam:ListAttachedRolePolicies",
          "iam:GetRole",
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:UpdateRole",
          "iam:UpdateRoleDescription",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:PassRole",
          "iam:ListInstanceProfilesForRole",
          "iam:RemoveRoleFromInstanceProfile",

        ]
        Resource = "*"
      },
      {
        Sid       = "AllowRemoveFromProfiles"
        Effect    = "Allow"
        Action    = "iam:RemoveRoleFromInstanceProfile"
        Resource  = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:instance-profile/clickstream-lakehouse-*"
      },
    ]
  })
}

# Attach policy to role
resource "aws_iam_role_policy_attachment" "github_actions" {
  for_each = toset(local.environments)

  role       = aws_iam_role.github_actions[each.value].name
  policy_arn = aws_iam_policy.github_actions[each.value].arn
}

# Output the role ARNs for easy reference
output "github_action_role_arns" {
  value = {
    for env in local.environments :
    env => aws_iam_role.github_actions[env].arn
  }
}
