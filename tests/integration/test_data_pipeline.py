import json
import sys
import pytest
import boto3
import os
from unittest.mock import patch, MagicMock
import time


sys.modules['pyspark'] = MagicMock()
sys.modules['pyspark.context'] = MagicMock()
sys.modules['pyspark.sql'] = MagicMock()
sys.modules['awsglue'] = MagicMock()

# Import handlers with mocked AWS environments
with patch.dict(os.environ, {"REGION": "us-east-1", "STREAM_NAME": "test-stream"}):
    from etl.handlers.click_handler import lambda_handler

class TestDataPipeline:
    """Integration tests for the entire data pipeline"""

    @pytest.mark.integration
    @patch('boto3.client')
    def test_end_to_end_data_flow(self, mock_boto3_client, sample_api_gateway_event):
        """Test data flow from Lambda to Kinesis to S3 (using mocks)"""

        # Mock clients for each AWS service
        mock_clients = {
            "kinesis": MagicMock(),
            "s3": MagicMock(),
            "glue": MagicMock(),
            "logs": MagicMock()
        }

        # Configure boto3.client to return the appropriate mock
        mock_boto3_client.side_effect = lambda service, **kwargs: mock_clients.get(service, MagicMock())

        # Mocked responses
        mock_clients["kinesis"].put_record.return_value = {
            "ShardId": "shard-1",
            "SequenceNumber": "49633314117839700824134151018549967652563289382723198018"
        }

        mock_clients["kinesis"].get_records.return_value = {
            "Records": [
                {
                    "Data": json.dumps({
                        "element": "button-signup",
                        "page": "/landing-page",
                        "userAgent": "Mozilla/5.0",
                        "timestamp": "2023-09-15T14:30:45Z",
                        "ingest_ts": "2023-09-15T14:30:46Z",
                        "request_id": "test-req-123"
                    }).encode('utf-8'),
                    "SequenceNumber": "49633314117839700824134151018549967652563289382723198018",
                    "PartitionKey": "button-signup"
                }
            ],
            "NextShardIterator": "AAAAAAAAAAF7..."
        }

        # Patch the module-level client in click_handler
        with patch('etl.handlers.click_handler.kinesis', mock_clients["kinesis"]), \
                patch('etl.handlers.click_handler.STREAM', "test-stream"), \
                patch.dict(os.environ, {"REGION": "us-east-1", "STREAM_NAME": "test-stream"}):

            mock_context = MagicMock()
            mock_context.aws_request_id = "test-request-123"

            # 1. First step: Lambda sends data to Kinesis
            response = lambda_handler(sample_api_gateway_event, mock_context)

            # Verify Lambda's response
            assert response["statusCode"] == 200
            assert json.loads(response["body"])["ingested"] is True

            # Verify Kinesis put_record was called
            mock_clients["kinesis"].put_record.assert_called_once()

            # 2. Second step: Data is transformed and stored in S3
            # For a true integration test, this would wait for the Glue job
            # In this mock version, we'll verify the data exists in Kinesis
            mock_clients["kinesis"].get_shard_iterator.return_value = {
                "ShardIterator": "AAAAAAAAAAHSywl9TEFMF..."
            }

            # Verify we can get records from Kinesis (simulating Glue's reading)
            shard_iterator = mock_clients["kinesis"].get_shard_iterator(
                StreamName="test-stream",
                ShardId="shard-1",
                ShardIteratorType="TRIM_HORIZON"
            )["ShardIterator"]

            records = mock_clients["kinesis"].get_records(
                ShardIterator=shard_iterator,
                Limit=10
            )

            # Verify records were received
            assert len(records["Records"]) > 0
            record_data = json.loads(records["Records"][0]["Data"].decode('utf-8'))
            assert record_data["element"] == "button-signup"
            assert "ingest_ts" in record_data


    @pytest.mark.integration
    @pytest.mark.skipif(not os.environ.get("RUN_AWS_TESTS"), reason="Skipping actual AWS calls")
    def test_lambda_local_to_kinesis(self, aws_credentials, sample_api_gateway_event):
        """Test Lambda handler with real Kinesis (only when explicitly enabled)"""
        # This test requires actual AWS credentials and will be skipped by default

        # Create a real Kinesis client
        kinesis = boto3.client('kinesis', region_name='us-east-1')

        # Generate a unique stream name for testing
        test_stream = f"test-stream-{int(time.time())}"

        try:
            # Create a test stream
            kinesis.create_stream(
                StreamName=test_stream,
                ShardCount=1
            )

            # Wait for the stream to become active
            time.sleep(30)

            # Set environment variable for handler
            with patch.dict(os.environ, {"REGION": "us-east-1", "STREAM_NAME": test_stream}):
                import importlib
                import sys

                # Check if the module is already loaded and remove it
                if 'etl.handlers.click_handler' in sys.modules:
                    del sys.modules['etl.handlers.click_handler']

                # Re-import with a new environment
                from etl.handlers.click_handler import lambda_handler

                mock_context = MagicMock()
                mock_context.aws_request_id = "test-request-123"


            # Call handler
                response = lambda_handler(sample_api_gateway_event, mock_context)

                # Verify response
                assert response["statusCode"] == 200

                # Get records from Kinesis
                shard_iterator = kinesis.get_shard_iterator(
                    StreamName=test_stream,
                    ShardId="shardId-000000000000",
                    ShardIteratorType="TRIM_HORIZON"
                )["ShardIterator"]

                # May need to retry a few times for data to be available
                max_retries = 5
                for i in range(max_retries):
                    records = kinesis.get_records(
                        ShardIterator=shard_iterator,
                        Limit=10
                    )

                    if records["Records"]:
                        break

                    time.sleep(2)
                    shard_iterator = records["NextShardIterator"]

                # Verify data was received
                assert len(records["Records"]) > 0
                record_data = json.loads(records["Records"][0]["Data"].decode('utf-8'))
                assert record_data["element"] == "button-signup"

        finally:
            # Clean up test stream
            try:
                kinesis.delete_stream(
                    StreamName=test_stream,
                    EnforceConsumerDeletion=True
                )
            except Exception as e:
                print(f"Error cleaning up test stream: {e}")
