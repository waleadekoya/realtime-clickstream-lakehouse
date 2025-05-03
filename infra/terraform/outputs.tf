output "kinesis_stream_name" { value = aws_kinesis_stream.click_stream.name }
output "raw_bucket_name" { value = aws_s3_bucket.raw_batch.bucket }
