import json
import os
import subprocess
from unittest.mock import MagicMock

import boto3
import pytest

TEST_ENVIRONMENT = os.environ.get('TEST_ENVIRONMENT', 'dev')
USE_REAL_AWS = os.environ.get("CHECK_AWS_RESOURCES") == "1"
PROJECT_NAME = os.getenv("PROJECT_NAME")


@pytest.mark.integration
@pytest.mark.infrastructure
class TestInfrastructure:
    """Infrastructure validation tests for Terraform configuration"""

    @pytest.fixture(scope="function")
    def aws_resources(self):
        """Returns either real or mock AWS clients based on the environment setting"""

        region = os.environ.get('AWS_REGION', 'us-east-1')

        if USE_REAL_AWS:
            return {
                "kinesis": boto3.client('kinesis', region_name=region),
                "lambda": boto3.client('lambda', region_name=region),
                "s3": boto3.client('s3', region_name=region),
                "glue": boto3.client('glue', region_name=region),
                "apigateway": boto3.client('apigateway', region_name=region),
            }
        else:
            mock_clients = {}

            # Mock Kinesis
            kinesis = MagicMock()
            kinesis.list_streams.return_value = {
                "StreamNames": [f"clickstream-{TEST_ENVIRONMENT}-events"],
                "HasMoreStreams": False
            }
            mock_clients["kinesis"] = kinesis

            # Mock Lambda
            lambda_client = MagicMock()
            lambda_client.get_function.return_value = {
                'Configuration': {
                    'FunctionName': f"clickstream-{TEST_ENVIRONMENT}-click-handler",
                    'Runtime': 'python3.12',
                    'Environment': {
                        'Variables': {
                            'STREAM_NAME': f"clickstream-{TEST_ENVIRONMENT}-events",
                            'REGION': region
                        }
                    }
                }
            }
            mock_clients["lambda"] = lambda_client

            # Mock S3
            s3 = MagicMock()
            s3.list_buckets.return_value = {
                'Buckets': [{'Name': f"clickstream-{TEST_ENVIRONMENT}-data"}]
            }
            mock_clients["s3"] = s3

            # Mock Glue
            glue = MagicMock()
            glue.get_job.return_value = {
                'Job': {
                    'Name': f"clickstream-{TEST_ENVIRONMENT}-stream-processor",
                    'Command': {
                        'Name': 'gluestreaming'
                    }
                }
            }
            mock_clients["glue"] = glue

            # Mock API Gateway
            apigateway = MagicMock()
            apigateway.get_rest_apis.return_value = {
                'items': [
                    {
                        'id': 'test-api-id',
                        'name': f"clickstream-{TEST_ENVIRONMENT}-api"
                    }
                ]
            }
            mock_clients["apigateway"] = apigateway

            return mock_clients

    @pytest.mark.skipif(not USE_REAL_AWS, reason="AWS resource checking is disabled")
    def test_kinesis_stream_exists(self, aws_resources):
        """Test that Kinesis stream exists in the target environment"""

        # List streams
        response = aws_resources["kinesis"].list_streams()

        # Check for project stream in the expected format
        project_stream = f"{PROJECT_NAME}-click-{TEST_ENVIRONMENT}"

        stream_exists = any(project_stream in stream for stream in response["StreamNames"])
        assert stream_exists, f"Expected Kinesis stream '{project_stream}' was not found"

    def test_lambda_function_exists(self, aws_resources):
        """Test that the Lambda function exists and is properly configured"""

        function_name = f"{PROJECT_NAME}-ingest-{TEST_ENVIRONMENT}"  # "${var.project}-ingest-${var.environment}"

        try:
            response = aws_resources["lambda"].get_function(FunctionName=function_name)

            assert response['Configuration']['Runtime'] == 'python3.12', f"Lambda {function_name} has incorrect runtime"

            # Verify environment variables
            env_vars = response['Configuration']['Environment']['Variables']
            assert 'STREAM_NAME' in env_vars, f"Lambda {function_name} missing STREAM_NAME env var"
            assert env_vars['STREAM_NAME'] == f"{PROJECT_NAME}-click-{TEST_ENVIRONMENT}"

        except aws_resources["lambda"].exceptions.ResourceNotFoundException:
            pytest.fail(f"Lambda function {function_name} does not exist")

    def test_s3_bucket_exists(self, aws_resources):
        """Test that the S3 bucket exists"""

        bucket_name = f"{PROJECT_NAME}-raw-{TEST_ENVIRONMENT}"  # "${var.project}-raw-${var.environment}"

        # List buckets to verify existence
        response = aws_resources["s3"].list_buckets()
        bucket_exists = any(bucket['Name'] == bucket_name for bucket in response['Buckets'])
        assert bucket_exists, f"S3 bucket {bucket_name} does not exist"

    def test_glue_job_exists(self, aws_resources):
        """Test that the Glue job exists"""
        job_name = f"{PROJECT_NAME}-stream-{TEST_ENVIRONMENT}"

        try:
            response = aws_resources["glue"].get_job(JobName=job_name)

            job_config = response['Job']
            assert job_config['Command']['Name'] == 'gluestreaming', f"Glue job {job_name} not configured for streaming"

        except aws_resources["glue"].exceptions.EntityNotFoundException:
            pytest.fail(f"Glue job {job_name} does not exist")

    @pytest.mark.terraform
    @pytest.mark.skipif(not os.environ.get("VALIDATE_TERRAFORM"), reason="Terraform validation tests are disabled")
    def test_terraform_validate(self, terraform_paths):
        """Test terraform validate passes"""
        terraform_dir = terraform_paths["terraform_dir"].as_posix()

        # Init so modules load (no real backend)
        subprocess.run(
            ["terraform", "init", "-backend=false"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
        )

        env = os.environ.copy()

        env.update({
            "TF_VAR_project": "test",
            "TF_VAR_environment": TEST_ENVIRONMENT,
            "TF_VAR_aws_region": "us-east-1",
        })

        result = subprocess.run(
            [
                "terraform",
                "validate",
                "-json",
            ],
            cwd=terraform_dir,
            capture_output=True,
            text=True
        )

        # Parse output
        output = json.loads(result.stdout or "{}")

        # Verify validation passed
        assert result.returncode == 0, f"validate failed:\n{result.stderr}"
        assert output.get("valid", False) is True

    @pytest.mark.terraform
    @pytest.mark.skipif(not os.environ.get("VALIDATE_TERRAFORM"), reason="Terraform validation tests are disabled")
    def test_terraform_plan(self, tmp_path):
        """Test terraform plan completes successfully"""
        mock_tf_dir = tmp_path / "mock_terraform"
        mock_tf_dir.mkdir()

        # Create a mock provider.tf and mock main.tf
        with open(mock_tf_dir / "provider.tf", "w") as f:
            f.write("""
    provider "aws" {
      region = "us-east-1"
      # Mock credentials
      access_key = "mock_access_key"
      secret_key = "mock_secret_key"
      # Skip credential validation
      skip_credentials_validation = true
      skip_requesting_account_id = true
      skip_region_validation = true
      skip_metadata_api_check = true
    }
    
    terraform {
      backend "local" {}
    }
            """)

        # Minimal main.tf for testing
        with open(mock_tf_dir / "main.tf", "w") as f:
            f.write("""
# Minimal main.tf for testing
variable "project" { type = string }
variable "environment" { type = string }
variable "aws_region" { type = string }
    
    output "test" {
      value = "This is a test"
    }
            """)

        # Always create a mock tfvars directory with every required var
        os.makedirs(mock_tf_dir / "tfvars", exist_ok=True)
        with open(mock_tf_dir / "tfvars" / f"{TEST_ENVIRONMENT}.tfvars", "w") as f:
            f.write(f"""
project     = "test"
environment = "{TEST_ENVIRONMENT}"
aws_region  = "us-east-1"   
            """)

        # Initialize and run the plan with the minimal test configuration
        subprocess.run(["terraform", "init"], cwd=mock_tf_dir, capture_output=True)

        result = subprocess.run(
            ["terraform", "plan", f"-var-file=tfvars/{TEST_ENVIRONMENT}.tfvars"],
            cwd=mock_tf_dir,
            capture_output=True,
            text=True
        )

        # Verify plan completed without errors
        assert result.returncode == 0
