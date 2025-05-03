# ---------- Kinesis Data Stream ----------
resource "aws_kinesis_stream" "click_stream" {
  name             = "${var.project}-click-${var.environment}"
  shard_count      = 5
  retention_period = 48 # hours, can be raised later
  tags             = local.tags
}

# ---------- Raw batch landing bucket ----------
resource "aws_s3_bucket" "raw_batch" {
  bucket        = "${var.project}-raw-${var.environment}"
  force_destroy = false
  tags          = local.tags
}
