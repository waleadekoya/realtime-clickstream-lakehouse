output "vpc_id" {
  description = "ID of the created VPC"
  value       = aws_vpc.glue_vpc.id
}

output "subnet_id" {
  description = "ID of the created subnet"
  value       = aws_subnet.glue_subnet.id
}

output "security_group_id" {
  description = "ID of the created security group"
  value       = aws_security_group.glue_sg.id
}

output "connection_name" {
  description = "Name of the created Glue connection"
  value       = aws_glue_connection.connection.name
}

output "connection_id" {
  description = "ID of the created Glue connection"
  value       = aws_glue_connection.connection.id
}

output "kinesis_endpoint_id" {
  value = aws_vpc_endpoint.kinesis.id
}
