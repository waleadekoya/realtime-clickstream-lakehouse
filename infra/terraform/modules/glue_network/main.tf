# Create S3 VPC Endpoint
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.glue_vpc.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.glue_route_table.id]

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-s3-endpoint"
    }
  )
}

# Create Glue VPC Endpoint
resource "aws_vpc_endpoint" "glue" {
  vpc_id              = aws_vpc.glue_vpc.id
  service_name        = "com.amazonaws.${var.region}.glue"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.glue_subnet.id]
  security_group_ids  = [aws_security_group.glue_sg.id]
  private_dns_enabled = true

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-glue-endpoint"
    }
  )
}

resource "aws_vpc_endpoint" "kinesis" {
  vpc_id              = aws_vpc.glue_vpc.id
  service_name        = "com.amazonaws.${var.region}.kinesis-streams"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.glue_subnet.id]
  security_group_ids  = [aws_security_group.glue_sg.id]
  private_dns_enabled = true

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-kinesis-endpoint"
    }
  )
}


# Create Cloudwatch Logs VPC Endpoint
resource "aws_vpc_endpoint" "logs" {
  vpc_id              = aws_vpc.glue_vpc.id
  service_name        = "com.amazonaws.${var.region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.glue_subnet.id]
  security_group_ids  = [aws_security_group.glue_sg.id]
  private_dns_enabled = true

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-logs-endpoint"
    }
  )
}

# Update the cleanup script to handle all VPC endpoints
resource "null_resource" "all_vpc_endpoints_cleanup" {
  triggers = {
    kinesis_endpoint_id = aws_vpc_endpoint.kinesis.id
    glue_endpoint_id    = aws_vpc_endpoint.glue.id
    logs_endpoint_id    = aws_vpc_endpoint.logs.id
    region              = var.region
  }

  provisioner "local-exec" {
    when    = destroy
    interpreter = ["bash", "-c"]
    command = <<-EOT
      echo "Ensuring proper cleanup of all VPC endpoints"

      # Create array of endpoint IDs
      ENDPOINT_IDS=("${self.triggers.kinesis_endpoint_id}" "${self.triggers.glue_endpoint_id}" "${self.triggers.logs_endpoint_id}")

      for ENDPOINT_ID in "$${ENDPOINT_IDS[@]}"; do
        echo "Processing VPC endpoint: $ENDPOINT_ID"

        # First attempt to delete the endpoint directly
        echo "Attempting to delete VPC endpoint..."
        aws ec2 delete-vpc-endpoints --region ${self.triggers.region} --vpc-endpoint-ids $ENDPOINT_ID || true

        # Wait a bit for deletion to take effect
        sleep 20

        # Check if endpoint is still around
        ENDPOINT_STATE=$(aws ec2 describe-vpc-endpoints --region ${self.triggers.region} --vpc-endpoint-ids $ENDPOINT_ID --query 'VpcEndpoints[0].State' --output text 2>/dev/null || echo "deleted")

        if [ "$ENDPOINT_STATE" != "deleted" ] && [ "$ENDPOINT_STATE" != "None" ]; then
          echo "VPC Endpoint still exists, state: $ENDPOINT_STATE"

          # Find ENIs associated with this endpoint
          ENDPOINT_ENIs=$(aws ec2 describe-network-interfaces --region ${self.triggers.region} --filters "Name=vpc-endpoint-id,Values=$ENDPOINT_ID" --query 'NetworkInterfaces[].NetworkInterfaceId' --output text)

          if [ ! -z "$ENDPOINT_ENIs" ]; then
            echo "Found ENIs associated with VPC endpoint: $ENDPOINT_ENIs"

            for ENI_ID in $ENDPOINT_ENIs; do
              echo "Working on ENI $ENI_ID"

              # Force detachment if attached
              ATTACHMENT_ID=$(aws ec2 describe-network-interfaces --region ${self.triggers.region} --network-interface-ids $ENI_ID --query 'NetworkInterfaces[0].Attachment.AttachmentId' --output text)

              if [ "$ATTACHMENT_ID" != "None" ] && [ "$ATTACHMENT_ID" != "null" ]; then
                echo "Detaching ENI $ENI_ID (attachment: $ATTACHMENT_ID)"
                aws ec2 detach-network-interface --region ${self.triggers.region} --attachment-id $ATTACHMENT_ID --force || true
                sleep 10  # Wait for detachment
              fi

              # Try to delete the ENI
              echo "Attempting to delete ENI $ENI_ID"
              aws ec2 delete-network-interface --region ${self.triggers.region} --network-interface-id $ENI_ID || true
            done
          fi

          # Try one more time to delete the endpoint
          echo "Retrying deletion of VPC endpoint..."
          aws ec2 delete-vpc-endpoints --region ${self.triggers.region} --vpc-endpoint-ids $ENDPOINT_ID || true
        else
          echo "VPC Endpoint successfully deleted or already gone"
        fi
      done
    EOT
  }

  depends_on = [
    aws_vpc_endpoint.kinesis,
    aws_vpc_endpoint.glue,
    aws_vpc_endpoint.logs
  ]
}


# Create VPC for Glue connection
resource "aws_vpc" "glue_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-vpc"
    }
  )

}

# Null resource to ensure cleanup of any lingering ENIs
resource "null_resource" "vpc_eni_cleanup" {
  triggers = {
    vpc_id = aws_vpc.glue_vpc.id
    region = var.region
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      echo "Waiting for all services to release ENIs..."
      sleep 30  # Give services time to start cleanup

      # Find any lingering ENIs in the VPC and detach/delete them
      for ATTEMPT in {1..5}; do
        echo "Cleanup attempt $ATTEMPT..."
        ENI_IDS=$(aws ec2 describe-network-interfaces --region ${self.triggers.region} --filters Name=vpc-id,Values=${self.triggers.vpc_id} --query 'NetworkInterfaces[].NetworkInterfaceId' --output text)

        if [ -z "$ENI_IDS" ]; then
          echo "No ENIs found, exiting cleanup"
          exit 0
        fi

        for ENI_ID in $ENI_IDS; do
          echo "Working on ENI $ENI_ID"

          # Check if ENI has an attachment
          ATTACHMENT_ID=$(aws ec2 describe-network-interfaces --region ${self.triggers.region} --network-interface-ids $ENI_ID --query 'NetworkInterfaces[0].Attachment.AttachmentId' --output text)

          if [ "$ATTACHMENT_ID" != "None" ] && [ "$ATTACHMENT_ID" != "null" ]; then
            echo "Detaching ENI $ENI_ID (attachment: $ATTACHMENT_ID)"
            aws ec2 detach-network-interface --region ${self.triggers.region} --attachment-id $ATTACHMENT_ID --force || true
            sleep 10  # Wait longer for detachment
          fi

          echo "Attempting to delete ENI $ENI_ID"
          aws ec2 delete-network-interface --region ${self.triggers.region} --network-interface-id $ENI_ID || true
        done

        sleep 30  # Wait between attempts
      done
    EOT
  }

  # depends_on = [aws_vpc.glue_vpc]
}

# Create subnet for Glue connection
resource "aws_subnet" "glue_subnet" {
  vpc_id            = aws_vpc.glue_vpc.id
  cidr_block        = var.subnet_cidr
  availability_zone = var.availability_zone

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-subnet"
    }
  )
  lifecycle {
    create_before_destroy = true
  }

}

# Create security group for Glue connection
resource "aws_security_group" "glue_sg" {
  name        = "${var.name_prefix}-glue-sg"
  description = "Security group for AWS Glue connection"
  vpc_id      = aws_vpc.glue_vpc.id

  # Outbound access to AWS services
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  # Allow all inbound traffic from the same security group
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  # Allow all outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-glue-sg"
    }
  )
  lifecycle {
    create_before_destroy = true
  }

}

# Create Internet Gateway
resource "aws_internet_gateway" "glue_igw" {
  vpc_id = aws_vpc.glue_vpc.id

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-igw"
    }
  )
}

#
resource "null_resource" "igw_detachment" {
  triggers = {
    igw_id = aws_internet_gateway.glue_igw.id
    vpc_id = aws_vpc.glue_vpc.id
  }

  provisioner "local-exec" {
    when    = destroy
    command = "aws ec2 detach-internet-gateway --internet-gateway-id ${self.triggers.igw_id} --vpc-id ${self.triggers.vpc_id} || true"
  }

  depends_on = [aws_internet_gateway.glue_igw]
}

# Create route table for the subnet
resource "aws_route_table" "glue_route_table" {
  vpc_id = aws_vpc.glue_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.glue_igw.id
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.name_prefix}-route-table"
    }
  )
}

# Associate route table with subnet
resource "aws_route_table_association" "glue_route_assoc" {
  subnet_id      = aws_subnet.glue_subnet.id
  route_table_id = aws_route_table.glue_route_table.id
}

# Create a Glue connection
resource "aws_glue_connection" "connection" {
  name            = var.connection_name
  connection_type = "NETWORK"

  physical_connection_requirements {
    availability_zone      = var.availability_zone
    security_group_id_list = [aws_security_group.glue_sg.id]
    subnet_id              = aws_subnet.glue_subnet.id
  }
}
