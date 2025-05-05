# 1. Glue Job Role
data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "glue_job" {
  name               = "${var.project}-glue-job-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
  tags               = { Project = var.project, Environment = var.environment }
}

data "aws_iam_policy_document" "glue_policy" {
  statement {
    sid = "ReadKinesis"
    actions = [
      "kinesis:GetRecords",
      "kinesis:GetShardIterator",
      "kinesis:ListShards"
    ]
    resources = [var.stream_arn]
  }
  statement {
    sid       = "WriteToS3"
    actions   = ["s3:PutObject", "s3:PutObjectAcl"]
    resources = ["${var.bucket_arn}/*"]
  }
  statement {
    sid       = "ReadFromS3"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${var.bucket_arn}/*"]
  }
  statement {
    sid       = "DeleteS3Objects"
    actions   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${var.bucket_arn}/*"]
  }
  statement {
    sid       = "ListS3Bucket"
    actions   = ["s3:ListBucket", "s3:ListBucketVersions"]
    resources = [var.bucket_arn]
  }

  statement {
    sid = "CloudWatchLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}
resource "aws_iam_role_policy" "glue_job_policy" {
  name   = "glue-job-inline-policy"
  role   = aws_iam_role.glue_job.id
  policy = data.aws_iam_policy_document.glue_policy.json
}

# Attach AWS managed Glue service role policy
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_job.id
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}


# 2. Step Functions Role
data "aws_iam_policy_document" "stepfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "step_functions" {
  name               = "${var.project}-sfn-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.stepfn_assume.json
  tags               = { Project = var.project, Environment = var.environment }
}

data "aws_iam_policy_document" "stepfn_policy" {
  statement {
    actions = [
      "glue:StartJobRun",
      "glue:GetJobRun",
      "glue:GetJobRuns"
    ]
    resources = ["*"]
  }
}
resource "aws_iam_role_policy" "stepfn_policy" {
  name   = "stepfn-inline-policy"
  role   = aws_iam_role.step_functions.id
  policy = data.aws_iam_policy_document.stepfn_policy.json
}


# 3 Ingest Lambda Role
resource "aws_iam_role" "lambda_exec" {
  name               = "${var.project}-ingest-lambda-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# Allow Lambda service to assume
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Inline policy: allow PutRecord to Kinesis & CloudWatch logs
data "aws_iam_policy_document" "lambda_policy" {
  statement {
    sid       = "WriteToKinesis"
    actions   = ["kinesis:PutRecord"]
    resources = [var.stream_arn]
  }
  statement {
    sid = "CloudWatchLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:aws:logs:${var.region}:*:*"]
  }
}

resource "aws_iam_role_policy" "lambda_exec_policy" {
  name   = "${var.project}-ingest-lambda-policy"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.lambda_policy.json
}
