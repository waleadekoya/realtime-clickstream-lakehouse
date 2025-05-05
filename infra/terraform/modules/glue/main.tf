# 1. Upload the Python script to S3
resource "aws_s3_object" "glue_script" {
  bucket       = var.scripts_bucket
  key          = "${var.project}/${var.environment}/glue_stream.py"
  source       = var.script_local_path
  etag         = filemd5(var.script_local_path)
  content_type = "text/x-python-script"
}

data "aws_caller_identity" "current" {}



# 2. Create the Glue streaming job
resource "aws_glue_job" "click_stream" {
  name     = "${var.project}-stream-${var.environment}"
  role_arn = var.role_arn

  command {
    name            = "gluestreaming"
    python_version  = "3"
    script_location = "s3://${var.scripts_bucket}/${aws_s3_object.glue_script.key}"
  }

  glue_version      = "5.0"
  worker_type = "G.1X"
  number_of_workers = 2

  # Connections for Kinesis
  connections = [var.connection_name]


  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-bookmark-option"              = "job-bookmark-enable"
    "--enable-glue-datacatalog"          = "true"
    "--TempDir"                          = "s3://${var.scripts_bucket}/${var.project}/${var.environment}/temp/"

    "--STREAM_NAME"                      = var.stream_name
    "--AWS_REGION"                       = var.region
    "--ENVIRONMENT"                      = var.environment
    "--S3_BRONZE_BUCKET"                 = var.bronze_bucket_name
    "--STREAM_ARN"                       = var.stream_arn

    # Delta Lake support
    "--datalake-formats"                 = "delta"

    # S3A credentials provider
    "--conf"                             = "spark.hadoop.fs.s3a.aws.credentials.provider=com.amazonaws.auth.DefaultAWSCredentialsProviderChain"

  }
  execution_property {
    max_concurrent_runs = 1
  }

}

# Null resource for cleanup
resource "null_resource" "glue_job_cleanup" {
  triggers = {
    job_name = aws_glue_job.click_stream.name
    region   = var.region
  }

  provisioner "local-exec" {
    when    = destroy
    command = "aws glue stop-job-run --job-name ${self.triggers.job_name} --region ${self.triggers.region} || true"
  }

  depends_on = [aws_glue_job.click_stream]
}
