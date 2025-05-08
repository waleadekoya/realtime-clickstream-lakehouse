import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pyspark.sql import SparkSession

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# Fixtures for mocking AWS services
@pytest.fixture
def mock_kinesis():
    with patch('boto3.client') as mock_client:
        mock_kinesis = MagicMock()
        mock_client.return_value = mock_kinesis
        yield mock_kinesis

@pytest.fixture
def mock_s3():
    with patch('boto3.client') as mock_client:
        mock_s3 = MagicMock()
        mock_client.return_value = mock_s3
        yield mock_s3

@pytest.fixture
def mock_glue():
    with patch('boto3.client') as mock_client:
        mock_glue = MagicMock()
        mock_client.return_value = mock_glue
        yield mock_glue

# Sample click event data fixture
@pytest.fixture
def sample_click_event():
    return {
        "element": "button-signup",
        "page": "/landing-page",
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "timestamp": "2023-09-15T14:30:45Z"
    }

@pytest.fixture
def sample_api_gateway_event(sample_click_event):
    return {
        "body": json.dumps(sample_click_event),
        "requestContext": {
            "requestId": "test-request-123"
        },
        "headers": {
            "Content-Type": "application/json"
        }
    }

# Mock SparkSession for testing Glue components
@pytest.fixture(scope="session")
def spark_session():
    """Create a SparkSession for tests"""
    spark = (SparkSession.builder
             .master("local[*]")
             .appName("pytest-spark")
             .config("spark.sql.shuffle.partitions", "1")
             .config("spark.sql.warehouse.dir", "/tmp/spark-warehouse")
             .config("spark.driver.host", "127.0.0.1")
             .getOrCreate())

    yield spark
    spark.stop()

@pytest.fixture
def mock_glue_context(spark_session):
    """Mock GlueContext for testing"""
    mock_context = MagicMock()
    mock_context.spark_session = spark_session
    mock_context.create_data_frame = MagicMock()
    return mock_context

# AWS environment variables fixture
@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for boto3"""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["REGION"] = "us-east-1"
    os.environ["STREAM_NAME"] = "test-stream"


def pytest_configure(config):
    """Set environment variables for tests"""
    os.environ["RUN_AWS_TESTS"] = "1"
    os.environ["VALIDATE_TERRAFORM"] = "1"
    os.environ["CHECK_AWS_RESOURCES"] = "1"
    os.environ["VALIDATE_TERRAFORM"] = "1"
    os.environ["PROJECT_NAME"] = "clickstream-lakehouse"

    # Register custom markers
    config.addinivalue_line("markers",
                            "integration: mark test as an integration test")
    config.addinivalue_line("markers",
                            "terraform: mark test as a terraform test")
    config.addinivalue_line("markers",
                            "infrastructure: mark test as infrastructure test")


@pytest.fixture(scope="session")
def terraform_paths():
    """Fixture to provide terraform paths and skip tests if needed"""
    project_root = Path(__file__).parents[1]
    terraform_dir = project_root / "infra" / "terraform"

    return {
        "project_root": project_root,
        "terraform_dir": terraform_dir
    }


@pytest.fixture(autouse=True)
def skip_if_terraform_missing(request, terraform_paths):
    """Skip tests that need terraform if the directory doesn't exist"""
    # Only apply to terraform tests
    if "terraform" in request.keywords:
        terraform_dir = terraform_paths["terraform_dir"]
        if not terraform_dir.exists():
            pytest.skip(f"Terraform directory not found at {terraform_dir}")

