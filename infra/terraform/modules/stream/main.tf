resource "aws_kinesis_stream" "this" {
  name             = "${var.project}-click-${var.environment}"
  shard_count      = 5
  retention_period = 48
  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

