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
    command = "python ${path.module}/scripts/cleanup_vpc_endpoints.py --region ${self.triggers.region} --endpoints ${self.triggers.kinesis_endpoint_id},${self.triggers.glue_endpoint_id},${self.triggers.logs_endpoint_id}"

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
    command = "python ${path.module}/scripts/cleanup_vpc_enis.py --region ${self.triggers.region} --endpoints ${self.triggers.vpc_id}"

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
