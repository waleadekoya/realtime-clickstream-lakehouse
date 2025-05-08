# AWS Real-Time Clickstream Analytics Pipeline

[![Terraform](https://img.shields.io/badge/Terraform-1.0+-blue.svg)](https://www.terraform.io/)
[![AWS](https://img.shields.io/badge/AWS-Serverless-orange.svg)](https://aws.amazon.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Overview

A enterprise-grade serverless streaming pipeline for real-time clickstream data processing, built with AWS services and
Infrastructure as Code principles.

### Key Features

- Serverless architecture with auto-scaling capabilities
- Real-time data ingestion and processing
- Delta Lake format support for ACID compliance
- Infrastructure as Code using Terraform
- Automated cleanup and resource management
- VPC networking with security best practices

## Architecture

![Architecture Diagram](docs/architecture.png)

### Components

1. **Data Ingestion Layer**
    - API Gateway endpoint for data reception
    - Lambda function for stream processing
    - Kinesis Data Streams for real-time data handling

2. **Processing Layer**
    - AWS Glue Streaming Job (G.1X workers)
    - Delta Lake format support
    - Continuous CloudWatch logging

3. **Storage Layer**
    - S3 buckets for raw and processed data
    - Data catalog integration
    - Delta Lake table format

4. **Network Layer**
    - Custom VPC configuration
    - Security groups and network ACLs
    - ENI management for Glue connectivity

## Prerequisites

- AWS Account with administrative access
- Terraform v1.0 or higher
- Python 3.12.0
- AWS CLI configured with appropriate credentials
- S3 bucket for Terraform state (manually created)
- virtualenv package manager

## Infrastructure Setup

### 1. Environment Preparation

1. **Create Terraform State Bucket:**

   ```bash
   aws s3api create-bucket --bucket clickstream-tfstate --region us-east-1
   ```

2. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/realtime-clickstream-lakehouse.git
   cd realtime-clickstream-lakehouse
   ```

3. **Setup Python Environment:**

   ```bash
   python -m virtualenv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

### 2. Terraform Deployment

1. **Initialize Terraform:**

   ```bash
   cd infrastructure
   terraform init
   ```

2. **Review the Plan:**

   ```bash
   terraform plan -var-file=environments/dev.tfvars
   ```

3. **Deploy the Infrastructure:**

   ```bash
   terraform apply -var-file=environments/dev.tfvars
   ```

### 3. Web Application Setup

The website in the `website/` directory is automatically configured during deployment. The Terraform process:

1. Injects the API Gateway URL into the HTML template
2. Creates an `index.html` file from the `index.template.html`
3. Configures all necessary connection parameters

To use the demo website:

1. Navigate to the website directory:
   ```bash
   cd website/
   ```
2. Start a local Python server:
   ```bash
   python -m http.server 8080
   ```
3. Navigate to `http://localhost:8080` to see the clickstream demo in action.

## Data Flow Explanation

1. **Event Generation:**
   - User interactions on the website generate click events
   - Events are sent to the API Gateway endpoint

2. **Data Ingestion:**
   - Lambda function processes incoming events
   - Events are placed into Kinesis Data Stream

3. **Stream Processing:**
   - AWS Glue job continuously reads from Kinesis
   - Data is transformed and enriched in real-time
   - Processed data is written in Delta Lake format to S3

4. **Data Storage:**
   - Data lands in the S3 bucket in Delta Lake format
   - Delta Lake ensures ACID properties and schema evolution
   - Data is available for querying via AWS Athena or other tools

## Monitoring and Maintenance

### Logs and Metrics

- **Lambda Logs:**
  ```bash
  aws logs describe-log-groups --log-group-name-prefix /aws/lambda/clickstream
  ```

- **Glue Job Metrics:**
  Monitor via AWS CloudWatch console or:
  ```bash
  aws cloudwatch get-metric-statistics --namespace AWS/Glue --metric-name glue.driver.aggregate.numCompletedTasks
  ```

### Resource Management

The infrastructure includes cleanup helpers for proper resource termination:

- Network resources (ENIs, security groups) are automatically cleaned up
- Glue jobs are stopped during terraform destroy
- S3 objects are versioned for data protection

## Customization

### Environment Variables

Modify `infrastructure/environments/*.tfvars` files to customize:

- AWS region
- Project name and environment
- VPC and subnet configuration
- Glue worker configurations

### Adding Custom Processing

To extend the ETL process:

1. Modify `etl/glue_stream.py` to add custom processing logic
2. Update Lambda handler in `etl/handlers/click_handler.py` for preprocessing
3. Run `terraform apply` to deploy the changes

## Troubleshooting

### Common Issues

1. **ENI Deletion Failures:**
   - The cleanup script addresses this, but you may need to manually delete ENIs if errors persist
   - Check the AWS console for orphaned ENIs in the VPC

2. **Glue Connectivity Issues:**
   - Verify the Glue connection via AWS console
   - Check security group rules to ensure proper access

3. **API Access Problems:**
   - Verify CORS settings in the API Gateway
   - Check Lambda execution role permissions

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
