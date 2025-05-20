output "api_invoke_url" {
  description = "API Gateway invoke URL for the ingest endpoint"
  value       = "${aws_api_gateway_stage.api_stage.invoke_url}/events"
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.ingest.function_name
}

output "api_id" {
  description = "The ID of the API Gateway REST API"
  value       = aws_api_gateway_rest_api.ingest_api.id
}





