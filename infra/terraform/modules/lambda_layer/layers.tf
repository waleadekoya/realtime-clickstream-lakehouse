# Simple layer upload and registration
resource "aws_s3_object" "lambda_layer" {
  bucket       = var.lambda_layer_s3_bucket
  key          = var.lambda_layer_s3_key

  source       = var.lambda_layer_local_path
  content_type = "application/zip"

  lifecycle {
    ignore_changes = all
  }
}

resource "aws_lambda_layer_version" "schema_registry_layer" {
  layer_name = "${var.project}-schema-registry-layer-${var.environment}"

  s3_bucket = var.lambda_layer_s3_bucket
  s3_key    = var.lambda_layer_s3_key

  compatible_runtimes = ["python3.12"]

  # Don't use source_code_hash for change detection since the file is created during apply
  # This prevents the "Provider produced inconsistent final plan" error
  lifecycle {
    ignore_changes = all
  }

  depends_on = [aws_s3_object.lambda_layer]
}
