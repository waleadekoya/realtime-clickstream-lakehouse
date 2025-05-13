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


# 0. Create the Lambda handler ZIP package - Zip up handler directory
data "archive_file" "handler_zip" {
  type        = "zip"
  source_file = local.handler_src
  output_path = local.zip_path

  depends_on = [local_file.ensure_build_dir]

}

# 1. Upload the Lambda ZIP to S3
resource "aws_s3_object" "lambda_zip" {
  bucket       = var.code_s3_bucket
  key          = var.code_s3_key
  source       = data.archive_file.handler_zip.output_path
  content_type = "application/zip"
  etag         = filemd5(data.archive_file.handler_zip.output_path)

}

# 2. Lambda Function (reuse role from modules/iam)
resource "aws_lambda_function" "ingest" {
  function_name = "${var.project}-ingest-${var.environment}"
  s3_bucket     = aws_s3_object.lambda_zip.bucket
  s3_key        = aws_s3_object.lambda_zip.key
  handler       = var.lambda_handler
  runtime       = var.lambda_runtime
  role          = var.lambda_role_arn
  timeout       = var.lambda_timeout

  source_code_hash = data.archive_file.handler_zip.output_base64sha256


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

  variables = {
    lambdaAlias = aws_lambda_alias.ingest_alias.name

  }

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}
