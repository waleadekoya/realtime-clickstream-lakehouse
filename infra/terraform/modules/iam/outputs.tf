output "glue_job_role_arn" {
  value = aws_iam_role.glue_job.arn
}

output "step_functions_role_arn" {
  value = aws_iam_role.step_functions.arn
}

output "lambda_exec_role_arn" {
  description = "IAM role arn for ingest Lambda (if enabled)"
  value       = aws_iam_role.lambda_exec.arn
}
