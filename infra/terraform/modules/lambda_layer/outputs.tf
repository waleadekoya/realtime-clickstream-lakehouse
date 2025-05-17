output "schema_registry_layer_arn" {
  description = "ARN of the schema registry Lambda layer"
  value       = aws_lambda_layer_version.schema_registry_layer.arn
}

output "schema_registry_layer_name" {
  description = "Name of the schema registry Lambda layer"
  value       = aws_lambda_layer_version.schema_registry_layer.layer_name
}
