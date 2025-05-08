import json
import os
from unittest.mock import patch, MagicMock

with patch.dict(os.environ, {"REGION": "us-east-1", "STREAM_NAME": "test-stream"}):
    from etl.handlers.click_handler import lambda_handler
    import etl.handlers.click_handler as click_handler_module

class TestClickHandler:
    """Unit tests for the Lambda click handler function"""

    def test_handler_successful_request(self, mock_kinesis, sample_api_gateway_event):
        """Test successful processing of a click event"""
        # Configure the mock to return a successful response
        mock_response = {"ShardId": "shardId-000000000000", "SequenceNumber": "49633314117839700824134151018549967652563289382723198018"}
        mock_kinesis.put_record.return_value = mock_response

        mock_context = MagicMock()
        mock_context.aws_request_id = "test-request-id"

        with patch.object(click_handler_module, 'kinesis', mock_kinesis):

            result = lambda_handler(sample_api_gateway_event, mock_context)

            # Verify the response
            assert result["statusCode"] == 200
            assert "application/json" in result["headers"]["Content-Type"]
            assert "ingested" in json.loads(result["body"])
            assert json.loads(result["body"])["ingested"] is True

            # Verify the Kinesis call
            mock_kinesis.put_record.assert_called_once()
            args, kwargs = mock_kinesis.put_record.call_args
            assert kwargs["StreamName"] == "test-stream"

            # Verify payload enrichment
            payload = json.loads(kwargs["Data"].decode("utf-8"))
            assert "ingest_ts" in payload
            assert "request_id" in payload

    def test_handler_invalid_json(self, mock_kinesis):
        """Test handler's response to invalid JSON in the body"""

        # Event with invalid JSON
        event = {"body": "{invalid json}"}

        with patch.object(click_handler_module, 'kinesis', mock_kinesis):

            result = lambda_handler(event, MagicMock())

            # Verify error response
            assert result["statusCode"] == 400
            assert "error" in json.loads(result["body"])
            assert "Invalid JSON" in json.loads(result["body"])["error"]

            # Verify Kinesis was not called
            mock_kinesis.put_record.assert_not_called()

    def test_handler_exception_handling(self, mock_kinesis, sample_api_gateway_event):
        """Test handler's exception handling"""

        # Mock to raise an exception
        mock_kinesis.put_record.side_effect = Exception("Test failure")

        with patch.object(click_handler_module, 'kinesis', mock_kinesis):

            result = lambda_handler(sample_api_gateway_event, MagicMock())

            # Verify error response
            assert result["statusCode"] == 500
            assert "error" in json.loads(result["body"])
            assert "Internal server error" in json.loads(result["body"])["error"]

    def test_handler_missing_element(self, mock_kinesis):
        """Test handler when an element is missing from the payload"""

        # Event with no element field
        event = {
            "body": json.dumps({
                "page": "/landing-page",
                "timestamp": "2023-09-15T14:30:45Z"
            })
        }

        # Configure the mock to return a successful response
        mock_kinesis.put_record.return_value = {"ShardId": "shard-1", "SequenceNumber": "seq-1"}

        mock_context = MagicMock()
        mock_context.aws_request_id = "test-request-id"

        with patch.object(click_handler_module, 'kinesis', mock_kinesis):

            result = lambda_handler(event, mock_context)

            assert result["statusCode"] == 200

            # Verify Kinesis call used "unknown" as the partition key
            args, kwargs = mock_kinesis.put_record.call_args
            assert kwargs["PartitionKey"] == "unknown"
