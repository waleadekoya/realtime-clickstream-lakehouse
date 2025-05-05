output "glue_job_name" {
  value = aws_glue_job.click_stream.name
}

output "glue_script_s3_path" {
  value = aws_s3_object.glue_script.id
}


