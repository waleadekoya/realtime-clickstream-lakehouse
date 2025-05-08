import json
import sys
from unittest.mock import patch, MagicMock

# Import the ETL functions directly (patching the SparkContext and GlueContext)
# Mock AWS Glue and PySpark imports first
sys.modules['awsglue.context'] = MagicMock()
sys.modules['awsglue.utils'] = MagicMock()

from etl.glue_stream import (
    _define_input_schema,
    _configure_spark_for_s3_parquet,
    check_for_kinesis_data,
    check_data_post_processing
)

class TestGlueStream:
    """Unit tests for Glue ETL components"""

    def test_define_input_schema(self):
        """Test that the schema definition is correct"""
        schema = _define_input_schema()

        # Verify schema has the expected fields
        field_names = [field.name for field in schema.fields]
        expected_fields = ["element", "page", "userAgent", "timestamp", "ingest_ts", "request_id"]

        assert len(schema.fields) == len(expected_fields)
        for field in expected_fields:
            assert field in field_names

    def test_check_kinesis_data(self, mock_kinesis):
        """Test Kinesis data checking function"""
        # Mock list_shards response
        mock_kinesis.list_shards.return_value = {
            "Shards": [{"ShardId": "shard-1"}]
        }

        # Mock get_shard_iterator response
        mock_kinesis.get_shard_iterator.return_value = {
            "ShardIterator": "iterator-1"
        }

        # Mock get_records with sample data
        mock_record = {
            "Data": json.dumps({
                "element": "button",
                "page": "/home",
                "timestamp": "2023-09-15T10:00:00Z"
            }).encode('utf-8'),
            "SequenceNumber": "seq-1",
            "PartitionKey": "button"
        }

        mock_kinesis.get_records.return_value = {
            "Records": [mock_record],
            "NextShardIterator": "next-iterator"
        }

        # Call function
        with patch('etl.glue_stream.logger') as mock_logger:
            check_for_kinesis_data("test-stream", "us-east-1")

            # Verify logs
            mock_logger.info.assert_any_call("Directly checking Kinesis stream for data...")
            mock_logger.info.assert_any_call("Stream has 1 shards")
            mock_logger.info.assert_any_call("Found 1 records in shard shard-1")

    def test_configure_spark_for_s3_parquet(self):
        """Test Spark configuration for S3/Parquet without requiring a real SparkSession"""
        # Mock SparkSession with a configuration holder
        mock_spark = MagicMock()
        mock_conf = {}

        # Mock the conf.set method to store values in our dictionary
        def mock_set(key, value):
            mock_conf[key] = value
            return mock_spark.conf

        # Mock the conf.get method to retrieve values from our dictionary
        def mock_get(key):
            return mock_conf.get(key)

        mock_spark.conf.set = mock_set
        mock_spark.conf.get = mock_get

        # Call the function being tested
        _configure_spark_for_s3_parquet(mock_spark)

        # Verify the configurations were set correctly
        assert mock_conf["spark.sql.shuffle.partitions"] == "1"
        assert mock_conf["spark.sql.streaming.minBatchesToRetain"] == "1"
        assert mock_conf["spark.sql.parquet.compression.codec"] == "snappy"
        assert mock_conf["spark.sql.parquet.mergeSchema"] == "false"
        assert mock_conf["spark.sql.parquet.filterPushdown"] == "true"


    def test_check_data_post_processing(self, mock_s3):
        """Test S3 output verification function"""
        # Mock S3 list_objects_v2 response
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "dev/bronze/clicks/file1.parquet", "Size": 1024},
                {"Key": "dev/bronze/clicks/file2.parquet", "Size": 2048}
            ]
        }

        # Call function
        with patch('etl.glue_stream.logger') as mock_logger:
            check_data_post_processing("test-bucket", "dev/bronze/clicks/", "us-east-1")

            # Verify logs
            mock_logger.info.assert_any_call("Checking for output files in S3 bucket 'test-bucket' with prefix 'dev/bronze/clicks/'")
            mock_logger.info.assert_any_call("Found 2 output item(s) in S3 at 'test-bucket/dev/bronze/clicks/'.")
