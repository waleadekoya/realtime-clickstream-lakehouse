resource "aws_s3_bucket" "raw" {
  bucket        = "${var.project}-raw-${var.environment}"
  force_destroy = true

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}


resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "null_resource" "s3_cleanup" {
  triggers = {
    bucket_name = aws_s3_bucket.raw.id
  }

  provisioner "local-exec" {
    when    = destroy
    command = "aws s3 rm s3://${self.triggers.bucket_name} --recursive"
  }
}
