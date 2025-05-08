terraform {
  backend "s3" {
    bucket = "clickstream-tfstate" # Note: must be created manually once
    key    = "state/terraform.tfstate"
    region = "us-east-1"

    # use_lockfile replaces the old dynamodb_table setting
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
}


# ---------- Kinesis Data Stream ----------
module "stream" {
  source      = "./modules/stream"
  project     = var.project
  environment = var.environment
}

# ---------- Raw batch landing bucket ----------
module "bucket" {
  source      = "./modules/bucket"
  project     = var.project
  environment = var.environment
}

module "iam" {
  source      = "./modules/iam"
  project     = var.project
  environment = var.environment
  stream_arn  = module.stream.stream_arn
  bucket_arn  = module.bucket.bucket_arn
  region      = var.aws_region
}

# ---------- Glue streaming job ----------
module "glue" {
  source            = "./modules/glue"
  project           = var.project
  environment       = var.environment
  role_arn          = module.iam.glue_job_role_arn
  scripts_bucket    = module.bucket.bucket_name
  script_local_path = "${path.module}/../../etl/glue_stream.py"

  stream_name       = module.stream.stream_name
  stream_arn        = module.stream.stream_arn
  region            = var.aws_region
  bronze_bucket_name = module.bucket.bucket_name  # Using existing bucket as bronze layer

  security_group_id = module.glue_network.security_group_id
  subnet_id         = module.glue_network.subnet_id
  connection_name   = module.glue_network.connection_name

  depends_on = [module.glue_network, module.iam, module.bucket]
}

module "glue_network" {
  source = "./modules/glue_network"

  name_prefix       = "${var.project}-${var.environment}"
  vpc_cidr          = var.vpc_cidr
  subnet_cidr       = var.subnet_cidr
  availability_zone = var.availability_zone
  connection_name   = "${var.project}-${var.environment}-kinesis-connection"
  region            = var.aws_region

  tags = {
    Project     = var.project
    Environment = var.environment
    Terraform   = "true"
  }

}

# ---------- Ingest API Lambda ----------
module "ingest_api" {
  source      = "./modules/ingest_api"
  project     = var.project
  environment = var.environment
  region      = var.aws_region

  # Kinesis stream details
  stream_arn  = module.stream.stream_arn
  stream_name = module.stream.stream_name

  # IAM role
  lambda_role_arn = module.iam.lambda_exec_role_arn

  # S3 key for the Lambda code & code packaging
  code_s3_bucket  = module.bucket.bucket_name
  code_local_path = "${path.module}/../../etl/handlers/click_handler.zip"
  code_s3_key     = "${var.project}/${var.environment}/click_handler.zip"

  lambda_handler = "click_handler.lambda_handler"

  depends_on = [module.bucket, module.stream, module.iam]

}


# Resource that ensures proper destruction order
resource "null_resource" "network_cleanup_helper" {
  # Use all the important resources as triggers
  triggers = {
    vpc_id = module.glue_network.vpc_id
    region = var.aws_region
  }

  # On destroy, wait for a bit to allow dependent resources to be properly released
  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      echo "Starting cleanup sequence..."

      # Wait for other resources to release their dependencies
      echo "Waiting for resources to release dependencies..."
      sleep 60

      # Help with ENI cleanup
      VPC_ID="${self.triggers.vpc_id}"
      echo "Looking for ENIs in VPC: $VPC_ID"
      ENI_IDS=$(aws ec2 describe-network-interfaces --region ${self.triggers.region} --filters Name=vpc-id,Values=$VPC_ID --query 'NetworkInterfaces[].NetworkInterfaceId' --output text)

      if [ ! -z "$ENI_IDS" ]; then
        for ENI_ID in $ENI_IDS; do
          echo "Found ENI: $ENI_ID, attempting to detach and delete"

          # Check if ENI has an attachment
          ATTACHMENT_ID=$(aws ec2 describe-network-interfaces --region ${self.triggers.region} --network-interface-ids $ENI_ID --query 'NetworkInterfaces[0].Attachment.AttachmentId' --output text)

          if [ "$ATTACHMENT_ID" != "None" ] && [ "$ATTACHMENT_ID" != "null" ]; then
            echo "Detaching ENI attachment: $ATTACHMENT_ID"
            aws ec2 detach-network-interface --region ${self.triggers.region} --attachment-id $ATTACHMENT_ID --force || true
            sleep 10
          fi

          # Try to delete the ENI
          echo "Deleting ENI: $ENI_ID"
          aws ec2 delete-network-interface --region ${self.triggers.region} --network-interface-id $ENI_ID || true
        done
      else
        echo "No ENIs found in VPC"
      fi

      echo "Cleanup sequence completed"
    EOT
  }
}

resource "null_resource" "inject_api_url_in_index" {
  depends_on = [module.ingest_api]

  # Force this to run on every apply using a timestamp or uuid
  triggers = {
    # This makes the resource recreate and run on every apply
    always_run = timestamp()
  }


  provisioner "local-exec" {
    command = <<EOT
      ${var.python_command} inject_api_url.py ${module.ingest_api.api_invoke_url}
    EOT
  }
}


