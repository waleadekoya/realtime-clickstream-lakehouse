output "kinesis_stream_name" {
  description = "Name of the Kinesis stream"
  value       = module.stream.stream_name
}

output "raw_bucket_name" {
  description = "Name of the raw S3 bucket"
  value       = module.bucket.bucket_name
}

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.glue_network.vpc_id
}

output "subnet_id" {
  description = "ID of the subnet"
  value       = module.glue_network.subnet_id
}

output "security_group_id" {
  description = "ID of the security group"
  value       = module.glue_network.security_group_id
}

output "connection_name" {
  description = "Name of the Glue connection"
  value       = module.glue_network.connection_name
}

output "glue_job_role_arn" {
  value = module.iam.glue_job_role_arn
}

output "stepfn_role_arn" {
  value = module.iam.step_functions_role_arn
}

output "glue_job" {
  value = module.glue.glue_job_name
}
output "glue_script_path" {
  value = module.glue.glue_script_s3_path
}

output "ingest_api_url" {
  description = "Invoke URL for the POST /events endpoint"
  value       = module.ingest_api.api_invoke_url
  sensitive   = false # Mark as sensitive since this is an endpoint URL

}

output "ingest_lambda_role" {
  description = "ARN of the ingest Lambda execution role"
  value       = module.iam.lambda_exec_role_arn
}

# Output registry and schema names for other modules to use
output "schema_registry_name" {
  value = module.glue.schema_registry_name
}

output "schema_name" {
  value = module.glue.schema_name
}



