output "api_invoke_url" {
  description = "API Gateway invoke URL for the ingest endpoint"
  value       = "${aws_api_gateway_stage.api_stage.invoke_url}/events"
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.ingest.function_name
}



