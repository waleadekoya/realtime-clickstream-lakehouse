# 1. Upload the Python script to S3
resource "aws_s3_object" "glue_script" {
  bucket       = var.scripts_bucket
  key          = "${var.project}/${var.environment}/glue_stream.py"
  source       = var.script_local_path
  etag         = filemd5(var.script_local_path)
  content_type = "text/x-python-script"
}

# ─── Upload Delta Lake core JAR ────────────────────────────────────────────
resource "aws_s3_object" "delta_core_jar" {
  bucket = var.scripts_bucket
  key = "${var.project}/${var.environment}/jars/${var.delta_jar_key}"
  source = "${path.module}/../../../../${var.delta_jar_source_path}"
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

    # Delta Lake support: include the Delta core JAR
    "--extra-jars"                       = "s3://${var.scripts_bucket}/${var.project}/${var.environment}/jars/${var.delta_jar_key}"

    # ── Inject DeltaLake static configs ────────────────────────────────────────
    "--conf"                            = "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension"
    "--conf"                            = "spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog"


  }
  execution_property {
    max_concurrent_runs = 1
  }
}

# Glue Database
resource "aws_glue_catalog_database" "clickstream_db" {
  name        = "${var.project}_${var.environment}_db"
  description = "Database for clickstream analytics"
}

# Glue Table for Delta Lake format data
resource "aws_glue_catalog_table" "clickstream_table" {
  name          = "${var.project}_clicks_${var.environment}"
  database_name = aws_glue_catalog_database.clickstream_db.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "delta"
    "delta.format"   = "delta"
    "delta.catalog"  = "Glue"
    "EXTERNAL"       = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${var.bronze_bucket_name}/${var.project}/${var.environment}/clicks/"
    input_format  = "org.apache.hadoop.hive.ql.io.SymlinkTextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "delta"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    # Schema definition for clickstream data
    columns {
      name = "event_id"
      type = "string"
    }
    columns {
      name = "timestamp"
      type = "timestamp"
    }
    columns {
      name = "user_id"
      type = "string"
    }
    columns {
      name = "page_url"
      type = "string"
    }
    columns {
      name = "event_type"
      type = "string"
    }
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
    command = "aws glue batch-stop-job-run --job-name ${self.triggers.job_name} --region ${self.triggers.region} || true"
  }

  depends_on = [aws_glue_job.click_stream]
}

