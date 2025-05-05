import sys
import time
import logging

import boto3
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from pyspark.sql.functions import col, from_json, to_timestamp, to_date
from pyspark.sql.types import StructType, StructField, StringType

# ─── Logging setup ───────────────────────────────────────────────────────────
logger = logging.getLogger("glue_stream")
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)s %(filename)s:%(lineno)d %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def check_for_kinesis_data(stream_name, aws_region):
    # ─── Direct check for Kinesis data ──────────────────────────────────────────
    try:
        logger.info("Directly checking Kinesis stream for data...")
        kinesis_client = boto3.client('kinesis', region_name=aws_region)

        # Get all shards
        response = kinesis_client.list_shards(StreamName=stream_name)
        shards = response.get('Shards', [])
        logger.info(f"Stream has {len(shards)} shards")

        # Check data in each shard
        data_found = False
        for shard in shards:
            shard_id = shard['ShardId']
            logger.info(f"Checking shard {shard_id}")

            # Get shard iterator
            iterator_response = kinesis_client.get_shard_iterator(
                StreamName=stream_name,
                ShardId=shard_id,
                ShardIteratorType='TRIM_HORIZON'
            )
            shard_iterator = iterator_response['ShardIterator']

            # Get records
            records_response = kinesis_client.get_records(
                ShardIterator=shard_iterator,
                Limit=10
            )

            records = records_response.get('Records', [])
            logger.info(f"Found {len(records)} records in shard {shard_id}")

            # Log sample record data
            if records:
                data_found = True
                for i, record in enumerate(records[:3]):  # Log up to 3 records
                    try:
                        data = record['Data'].decode('utf-8')
                        logger.info(f"Sample record {i + 1}: {data[:500]}...")  # Truncate long records
                    except Exception as err:
                        logger.warning(f"Error decoding record: {err}")

        if not data_found:
            logger.warning("No data found in any shard with direct Kinesis API check")
    except Exception as err:
        logger.error(f"Error checking Kinesis directly: {err}", exc_info=True)


def run_glue_job():
    # ─── Read job args ──────────────────────────────────────────────────────────
    args = getResolvedOptions(
        sys.argv,
        ["JOB_NAME", "STREAM_ARN", "AWS_REGION", "ENVIRONMENT", "S3_BRONZE_BUCKET"]
    )
    JOB_NAME = args["JOB_NAME"]
    STREAM_ARN = args["STREAM_ARN"]
    AWS_REGION = args["AWS_REGION"]
    ENVIRONMENT = args["ENVIRONMENT"]
    S3_BRONZE_BUCKET = args["S3_BRONZE_BUCKET"]

    logger.info(f"Starting job {JOB_NAME} → stream {STREAM_ARN}")

    # Extract stream name from ARN
    stream_name = STREAM_ARN.split('/')[-1]
    logger.info(f"Extracted stream name: {stream_name}")

    check_for_kinesis_data(stream_name, AWS_REGION)

    # ─── Init Glue & Spark ──────────────────────────────────────────────────────
    sc = SparkContext.getOrCreate()
    glueContext = GlueContext(sc)
    spark = glueContext.spark_session
    spark.sparkContext.setLogLevel("WARN")
    logger.info("GlueContext & SparkSession initialized")

    # ─── Define JSON schema ─────────────────────────────────────────────────────
    schema = StructType([
        StructField("element", StringType(), True),
        StructField("page", StringType(), True),
        StructField("userAgent", StringType(), True),
        StructField("timestamp", StringType(), True),
        StructField("ingest_ts", StringType(), True),
        StructField("request_id", StringType(), True),
    ])
    logger.info("Schema for JSON payload defined")

    # ─── Read from Kinesis ──────────────────────────────────────────────────────
    kinesis_opts = {
        "streamARN": STREAM_ARN,
        "startingPosition": "TRIM_HORIZON",  # Changed from LATEST to read from the oldest available data
        "classification": "json",
        "inferSchema": "true"
    }
    logger.info(f"Reading from Kinesis stream {STREAM_ARN} with options: {kinesis_opts}")
    raw_df = glueContext.create_data_frame.from_options(
        connection_type="kinesis",
        connection_options=kinesis_opts
    )
    logger.info("Raw DataFrame schema:")
    raw_df.printSchema()

    # ─── Check if data exists ──────────────────────────────────────────────────
    # Note: With streaming DFs we can't directly check if empty, but we can check schema
    cols = raw_df.columns
    if len(cols) == 0:
        logger.info("No data in stream - exiting job early")
        return

    # ─── Identify columns ───────────────────────────────────────────────────────
    cols = raw_df.columns
    json_col = cols[0]  # the inferred JSON blob column
    arrival_col = cols[1] if len(cols) > 1 else None

    # ─── Cast & parse JSON ─────────────────────────────────────────────────────
    exprs = [f"CAST(`{json_col}` AS STRING) AS json_str"]
    if arrival_col:
        exprs.append(f"`{arrival_col}` AS ingest_ts")

    parsed_df = (
        raw_df
        .selectExpr(*exprs)
        .select(from_json(col("json_str"), schema).alias("payload"))
        .select("payload.*")
    )
    logger.info("Parsed DataFrame schema (after JSON parsing):")
    parsed_df.printSchema()

    # ─── Convert event timestamp ────────────────────────────────────────────────
    df2 = parsed_df.withColumn("event_ts", to_timestamp(col("timestamp")))
    logger.info("DataFrame schema with event_ts:")
    df2.printSchema()

    # ─── Write stream to S3 ─────────────────────────────────────────────────────
    out_path = f"s3://{S3_BRONZE_BUCKET}/{ENVIRONMENT}/bronze/clicks/"
    chkpt_path = f"s3://{S3_BRONZE_BUCKET}/{ENVIRONMENT}/checkpoints/clicks/"
    logger.info(f"Writing to {out_path} (checkpoints at {chkpt_path})")

    # ─── Add a daily partition key ───────────────────────────────────────────────
    df3 = df2.withColumn("event_date", to_date(col("event_ts")))

    logger.info("Showing df3 schema and sample data:")
    df3.printSchema()

    # Sample the first few records from the streaming DataFrame with a timeout
    sample_data = []

    def collect_sample(batch_df, batch_id):
        if batch_df.count() > 0 and len(sample_data) == 0:
            # Take at most 5 records from the first non-empty batch
            rows = batch_df.limit(5).collect()
            for row in rows:
                sample_data.append(row.asDict())
            logger.info(f"Collected {len(sample_data)} sample records from batch {batch_id}")

    # Run a quick-sampling query to collect data
    sample_query = (
        df3.coalesce(1)
        .writeStream
        .foreachBatch(collect_sample)
        .outputMode("append")
        .trigger(once=True)  # Process available data at once and terminate
        .start()
    )

    # Wait for the sampling to complete with a timeout
    logger.info("Waiting for sample data (max 30 seconds)...")
    start_time = time.time()
    timeout = 30  # 30-second timeout for sampling

    try:
        # Wait with timeout
        sample_query.awaitTermination(timeout)

        # Check if we timed out or completed normally
        if time.time() - start_time >= timeout:
            logger.info("Sample collection timed out - no data received within timeout period")
        else:
            logger.info("Sample collection completed normally")
    except Exception as err:
        logger.warning(f"Error during sample collection: {err}")
    finally:
        # Always try to stop the query
        try:
            if sample_query.isActive:
                sample_query.stop()
                logger.info("Sample query stopped")
        except Exception as err:
            logger.warning(f"Error stopping sample query: {err}")

        # Log the sample data if any was collected
    if sample_data:
        logger.info("Sample records from df3:")
        for idx, record in enumerate(sample_data, start=1):
            logger.info(f"Record {idx}: {record}")
    else:
        logger.info("No sample records collected from df3 (stream might be empty)")

    # ─── Fully-managed streaming sink ───────────────────────────────────────────

    # Configure Spark specifically for S3 and Parquet
    spark.conf.set("spark.sql.shuffle.partitions", "1")  # Use minimal partitions
    spark.conf.set("spark.sql.streaming.minBatchesToRetain", "1")  # Keep a minimal history

    # Configure Spark for better S3 Parquet writing
    logger.info("Configuring Spark for S3 and Parquet writing...")
    spark.conf.set("spark.sql.shuffle.partitions", "1")
    spark.conf.set("spark.sql.parquet.compression.codec", "snappy")
    spark.conf.set("spark.sql.parquet.mergeSchema", "false")  # Important - disable schema merging
    spark.conf.set("spark.sql.parquet.filterPushdown", "true")

    logger.info("Ensuring consistent data types for Parquet conversion...")
    df3 = df3.select(
        col("element").cast("string"),
        col("page").cast("string"),
        col("userAgent").cast("string"),
        col("timestamp").cast("string"),
        col("ingest_ts").cast("string"),
        col("request_id").cast("string"),
        col("event_ts"),
        col("event_date")
    )

    # Log schema after casting
    logger.info("DataFrame schema after type casting:")
    df3.printSchema()

    logger.info(f"Starting micro-batch processing at {time.time()}...")

    query = (
        df3.writeStream
        .format("parquet")
        .outputMode("append")
        .option("path", out_path)
        .option("checkpointLocation", chkpt_path)
        .option("mergeSchema", "true")
        .partitionBy("event_date")
        .trigger(availableNow=True)  # Process all available data in one batch
        .start()
    )
    logger.info(f"Query started with ID {query.id}")

    # Wait for the query to complete instead of using a timeout
    logger.info("Waiting for query to complete...")
    query.awaitTermination()  # Wait for the job to finish
    logger.info("Query completed successfully")

    def check_data_post_processing():
        # Add after processing completes
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        try:
            logger.info(f"Checking for output files in: {out_path}")
            response = s3_client.list_objects_v2(
                Bucket=S3_BRONZE_BUCKET,
                Prefix=f"{ENVIRONMENT}/bronze/clicks/"
            )

            if 'Contents' in response:
                for item in response['Contents']:
                    logger.info(f"Found output file: {item['Key']} ({item['Size']} bytes)")
            else:
                logger.warning("No output files found!")
        except Exception as exc:
            logger.error(f"Error checking for output files: {exc}", exc_info=True)

    check_data_post_processing()

    # Allows the job to complete naturally with success status
    logger.info("Job completed successfully")
    return


if __name__ == "__main__":
    start = time.time()
    try:
        run_glue_job()
    except Exception as e:
        logger.error(f"Job failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        elapsed = time.time() - start
        logger.info(f"Job runtime: {elapsed:.2f}s")
