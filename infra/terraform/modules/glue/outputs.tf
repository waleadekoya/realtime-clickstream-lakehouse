output "glue_job_name" {
  value = aws_glue_job.click_stream.name
}

output "glue_script_s3_path" {
  value = aws_s3_object.glue_script.id
  description = "S3 path to the Glue script"
}

output "schema_registry_name" {
  value = "${var.project}-${var.environment}-registry"
  description = "Name of the created Glue Schema Registry"
}

output "schema_name" {
  value = "${var.project}-clickstream-schema-${var.environment}"
  description = "Name of the created Glue Schema"
}
