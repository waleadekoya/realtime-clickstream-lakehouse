locals {
  # infra/terraform ──↑
  #                ../..  → realtime-clickstream-lakehouse/etl/handlers
  handler_src = "${path.root}/../../etl/handlers/click_handler.py"


  # location to write the ZIP
  zip_path    = "${path.module}/build/click_handler.zip"

  # Calculate hash of the source file
  source_hash = filebase64sha256(local.handler_src)

}

# Create the build directory if it doesn't exist
resource "local_file" "ensure_build_dir" {
  filename = "${path.module}/build/.keep"
  content  = "This file ensures the build directory exists"
}

# Create a copy of the source file with the correct name for Lambda
# Also create a copy with a hash in the name to force archive_file to refresh
resource "local_file" "source_file_copy" {
  filename = "${path.module}/tmp/click_handler.py"
  content  = file(local.handler_src)

  # Create the tmp directory if it doesn't exist
  provisioner "local-exec" {
    # Use Python script for cross-platform compatibility
    # Use relative path without quotes to avoid Windows path issues
    command = "${var.python_command} ${path.root}\\scripts\\create_directory.py ${path.module}\\tmp"
  }
}

# Create the Lambda handler ZIP package - Zip up handler directory
data "archive_file" "handler_zip" {
  type        = "zip"
  source_file = local_file.source_file_copy.filename
  output_path = local.zip_path

  depends_on = [local_file.ensure_build_dir, local_file.source_file_copy]

}

# Upload the Lambda ZIP to S3
resource "aws_s3_object" "lambda_zip" {
  bucket       = var.code_s3_bucket
  key          = var.code_s3_key
  source       = data.archive_file.handler_zip.output_path
  content_type = "application/zip"

  # Use the source hash to ensure this is updated when the source file changes
  # This is more reliable than using the etag of the zip file
  etag         = local.source_hash

}

# Force recreation of the Lambda function when the source file changes
resource "null_resource" "lambda_source_update_trigger" {
  # This will change whenever the source file changes
  triggers = {
    source_hash = local.source_hash
  }
}

# Lambda Function (reuse role from modules/iam)
resource "aws_lambda_function" "ingest" {
  function_name = "${var.project}-ingest-${var.environment}"
  s3_bucket     = aws_s3_object.lambda_zip.bucket
  s3_key        = aws_s3_object.lambda_zip.key
  handler       = var.lambda_handler
  runtime       = var.lambda_runtime
  role          = var.lambda_role_arn
  timeout       = var.lambda_timeout

  # Use the source_code_hash passed from the parent module if provided, otherwise use the calculated hash
  source_code_hash = var.source_code_hash != null ? var.source_code_hash : data.archive_file.handler_zip.output_base64sha256

  # Depend on the trigger resource to force recreation when the source file changes
  depends_on = [null_resource.lambda_source_update_trigger]

  # Using container image
  # package_type = "Image"
  # image_uri    = "${aws_ecr_repository.lambda_repo.repository_url}:latest"

  # Add Lambda layers
  layers = var.lambda_layers

  environment {
    variables = {
      STREAM_NAME = var.stream_name
      REGION      = var.region
      REGISTRY_NAME = var.registry_name
      SCHEMA_NAME   = var.schema_name
    }
  }

  tags = {
    Project     = var.project
    Environment = var.environment
  }

  publish = true

  lifecycle {
    create_before_destroy = true
  }

  # depends_on = [
  #   null_resource.build_lambda_image
  # ]

}

# 2) Create an alias
resource "aws_lambda_alias" "ingest_alias" {
  name             = var.environment    # e.g. "staging"
  function_name    = aws_lambda_function.ingest.function_name
  function_version = aws_lambda_function.ingest.version
}


# Allow API Gateway to invoke the Lambda
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.ingest_api.execution_arn}/*/${aws_api_gateway_method.post_events.http_method}${aws_api_gateway_resource.events.path}"

}

# ── API Gateway REST API ───
resource "aws_api_gateway_rest_api" "ingest_api" {
  name        = "${var.project}-ingest-api-${var.environment}"
  description = "API to ingest click events into Kinesis"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

resource "aws_api_gateway_resource" "events" {
  rest_api_id = aws_api_gateway_rest_api.ingest_api.id
  parent_id   = aws_api_gateway_rest_api.ingest_api.root_resource_id
  path_part   = "events"
}

# POST /events
resource "aws_api_gateway_method" "post_events" {
  rest_api_id   = aws_api_gateway_rest_api.ingest_api.id
  resource_id   = aws_api_gateway_resource.events.id
  http_method   = "POST"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "post_integration" {
  rest_api_id             = aws_api_gateway_rest_api.ingest_api.id
  resource_id             = aws_api_gateway_resource.events.id
  http_method             = aws_api_gateway_method.post_events.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.ingest.invoke_arn
}

# CORS: OPTIONS /events
resource "aws_api_gateway_method" "options" {
  rest_api_id   = aws_api_gateway_rest_api.ingest_api.id
  resource_id   = aws_api_gateway_resource.events.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_method_response" "options_response" {
  rest_api_id = aws_api_gateway_rest_api.ingest_api.id
  resource_id = aws_api_gateway_resource.events.id
  http_method = aws_api_gateway_method.options.http_method
  status_code = "200"
  response_models = {
    "application/json" = "Empty"
  }
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration" "options_integration" {
  rest_api_id = aws_api_gateway_rest_api.ingest_api.id
  resource_id = aws_api_gateway_resource.events.id
  http_method = aws_api_gateway_method.options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = <<EOF
{"statusCode": 200}
EOF
  }
}

# Add a separate integration response resource
resource "aws_api_gateway_integration_response" "options_integration_response" {
  rest_api_id = aws_api_gateway_rest_api.ingest_api.id
  resource_id = aws_api_gateway_resource.events.id
  http_method = aws_api_gateway_method.options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,X-Amz-Date,Authorization,X-Api-Key'"
    "method.response.header.Access-Control-Allow-Methods" = "'OPTIONS,POST'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [
    aws_api_gateway_method_response.options_response,
    aws_api_gateway_integration.options_integration
  ]
}


# ── Deployment & Stage ───
resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.ingest_api.id

  # Force a new deployment when integration or methods change
  triggers = {
    redeployment = sha1(jsonencode({
      methods      = aws_api_gateway_method.post_events.*.http_method
      integrations = aws_api_gateway_integration.post_integration.*.uri
    }))
  }

  depends_on = [
    aws_api_gateway_integration.post_integration,
    aws_api_gateway_integration.options_integration,
    aws_api_gateway_integration_response.options_integration_response,
    aws_api_gateway_method.post_events,
    aws_api_gateway_method.options
  ]

}

resource "aws_api_gateway_stage" "api_stage" {
  rest_api_id   = aws_api_gateway_rest_api.ingest_api.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = var.environment

  # variables = {
  #   lambdaAlias = aws_lambda_alias.ingest_alias.name
  #
  # }

  tags = {
    Project     = var.project
    Environment = var.environment
  }

  # Ensures the stage is updated before the old deployment is destroyed
  lifecycle {
    create_before_destroy = true
  }

}


# Create ECR repository
resource "aws_ecr_repository" "lambda_repo" {
  name = "${var.project}-ingest-${var.environment}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

#
# # Build and push the Docker image
# locals {
#   is_windows = contains(regexall("^[A-Za-z]:\\\\", abspath(path.root)), abspath(path.root))
# }
#
# resource "null_resource" "build_lambda_image" {
#   # Rebuild when handler or Dockerfile changes
#   triggers = {
#     handler_hash    = filebase64sha256(var.code_local_path)
#     dockerfile_hash = filebase64sha256("${path.module}/Dockerfile")
#   }
#
#   provisioner "local-exec" {
#     # Choose PowerShell on Windows, Bash elsewhere
#     interpreter = ["bash","-c"]
#
#     command = <<-EOT
#       # Set the build context to the project root directory
#
#       mkdir -p "${path.module}/tmp"
#       cp "${local.handler_src}" \
#          "${path.module}/tmp/click_handler.py"
#
#       # Build image
#       docker build -t ${var.project}-ingest-${var.environment} \
#         --file ${path.module}/Dockerfile \
#         --build-arg LAMBDA_TASK_ROOT="/var/task" \
#         ${path.module}
#
#       # Tag & push to ECR
#       docker tag ${var.project}-ingest-${var.environment} \
#         ${aws_ecr_repository.lambda_repo.repository_url}:latest
#       aws ecr get-login-password --region ${var.region} \
#         | docker login --username AWS --password-stdin ${aws_ecr_repository.lambda_repo.repository_url}
#       docker push ${aws_ecr_repository.lambda_repo.repository_url}:latest
#     EOT
#   }
#
#   depends_on = [aws_ecr_repository.lambda_repo]
# }
