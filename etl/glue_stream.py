import logging
import sys
import time

import boto3
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
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


def _get_job_args():
    logger.info("Reading job arguments...")
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "STREAM_ARN",
            "AWS_REGION",
            "ENVIRONMENT",
            "S3_BRONZE_BUCKET",
            "glue.schemaRegistry.registryName",
            "glue.schemaRegistry.schemaName",
            "glue.schemaRegistry.region",
            "glue.schemaRegistry.dataFormat",
        ]
    )
    logger.info(f"Job arguments received: {args}")
    return args


def _initialize_spark_glue():
    logger.info("Initializing SparkContext and GlueContext...")
    sc = SparkContext.getOrCreate()
    glueContext = GlueContext(sc)
    spark = glueContext.spark_session
    spark.sparkContext.setLogLevel("WARN")
    logger.info("GlueContext & SparkSession initialized.")

    # ─── Delta Lake support ────────────────────────────────────────────
    logger.info("GlueContext & SparkSession initialized (Delta configs injected by Glue job args).")

    return glueContext, spark


def _define_input_schema():
    logger.info("Defining JSON input schema...")
    schema = StructType([
        StructField("element", StringType(), True),
        StructField("page", StringType(), True),
        StructField("userAgent", StringType(), True),
        StructField("timestamp", StringType(), True),
        StructField("ingest_ts", StringType(), True),
        StructField("request_id", StringType(), True),
    ])
    logger.info("Schema for JSON payload defined.")
    return schema


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


def _read_from_kinesis_stream(glue_context, stream_arn, aws_region, registry_name, schema_name, data_format):
    stream_name = stream_arn.split('/')[-1]
    logger.info(f"Extracted stream name: {stream_name}")
    check_for_kinesis_data(stream_name, aws_region)  # Initial check


    logger.info(f"Using schema registry: {registry_name}, schema: {schema_name}")

    kinesis_opts = {
        "streamARN": stream_arn,
        "startingPosition": "TRIM_HORIZON",
        "classification": data_format.lower(),
        "inferSchema": "false",  # use the registry
        "validateSchema": "true",
        "awsGlueSchemaRegistryName": registry_name,
        "awsGlueSchemaRegistrySchemaName": schema_name,
    }
    logger.info(f"Reading from Kinesis stream {stream_arn} with Schema Registry validation options: {kinesis_opts}")

    try:

        raw_df = glue_context.create_data_frame.from_options(
            connection_type="kinesis",
            connection_options=kinesis_opts
        )
        logger.info("Raw DataFrame schema from Kinesis with Schema Registry validation:")
        raw_df.printSchema()
    except Exception as err:
        logger.error(f"Error reading from Kinesis with Schema Registry validation: {e}", exc_info=True)
        fallback_opts = {
            "streamARN": stream_arn,
            "startingPosition": "TRIM_HORIZON",
            "classification": "json",
            "inferSchema": "true"
        }
        raw_df = glue_context.create_data_frame.from_options(
            connection_type="kinesis",
            connection_options=fallback_opts
        )
        logger.warning("Reading without schema validation succeeded")

    if not raw_df.columns:
        logger.warning("No data columns found in Kinesis stream after read. Exiting job.")
        return None
    return raw_df


def _transform_data(raw_df, json_schema):
    logger.info("Starting data transformation...")
    # cols = raw_df.columns
    # if not cols:
    #     logger.warning("Raw DataFrame is empty, cannot transform.")
    #     return raw_df  # Return empty DF

    # json_col_name = cols[0]  # Assuming the first column is the JSON blob
    # arrival_col_name = cols[1] if len(cols) > 1 else None

    # exprs = [f"CAST(`{json_col_name}` AS STRING) AS json_str"]
    # if arrival_col_name:
    #     exprs.append(
    #         f"`{arrival_col_name}` AS arrival_ingest_ts")  # Use a distinct name if already present in json_schema

    # parsed_df = (
    #     raw_df
    #     .selectExpr(*exprs)
    #     .select(from_json(col("json_str"), json_schema).alias("payload"))
    #     .select("payload.*")
    # )
    # logger.info("Parsed DataFrame schema (after JSON parsing):")
    if not raw_df.columns:
        logger.warning("Raw DataFrame is empty, cannot transform.")
        return raw_df
    parsed_df = raw_df  # each field already a column after SR deserialisation
    parsed_df.printSchema()
    parsed_df.select("timestamp", "event_ts", "event_date").show(5, truncate=False)

    # Use 'ingest_ts' from JSON payload if present, otherwise use Kinesis arrival time
    # This assumes 'ingest_ts' in your schema is the preferred one.
    # If Kinesis arrival time is different and also needed, ensure the column names are distinct.
    # For simplicity, this example prioritizes 'ingest_ts' from the JSON payload if it exists.
    iso_fmt = "yyyy-MM-dd'T'HH:mm:ss[.SSS]X"
    df_with_event_ts = (
        parsed_df.withColumn(
            "event_ts", to_timestamp(col("timestamp"), iso_fmt))
    )
    logger.info("DataFrame schema with event_ts:")
    df_with_event_ts.printSchema()
    parsed_df.select("timestamp", "event_ts", "event_date").show(5, truncate=False)

    df_with_event_date = df_with_event_ts.withColumn("event_date", to_date(col("event_ts")))
    logger.info("DataFrame schema with event_date (partition key):")
    df_with_event_date.printSchema()
    return df_with_event_date


def _collect_sample_data(df, timeout_seconds=30):
    logger.info("Attempting to collect sample data...")
    sample_data = []

    def collect_batch_sample(batch_df, batch_id):
        if not sample_data and batch_df.count() > 0:  # Collect only from the first non-empty batch
            logger.info(f"Collecting samples from batch {batch_id}...")
            rows = batch_df.limit(5).collect()
            for row in rows:
                sample_data.append(row.asDict())
            logger.info(f"Collected {len(sample_data)} sample records.")

    sample_query = (
        df.coalesce(1)
        .writeStream
        .foreachBatch(collect_batch_sample)
        .outputMode("append")
        .trigger(once=True)
        .start()
    )

    logger.info(f"Waiting for sample data collection (max {timeout_seconds} seconds)...")
    start_time = time.time()
    try:
        sample_query.awaitTermination(timeout_seconds)
        if time.time() - start_time >= timeout_seconds and not sample_data:
            logger.info("Sample collection timed out - no data received within the period.")
        else:
            logger.info("Sample collection process completed.")
    except Exception as err:
        logger.warning(f"Error during sample collection: {err}", exc_info=True)
    finally:
        if sample_query.isActive:
            try:
                sample_query.stop()
                logger.info("Sample query stopped.")
                return None
            except Exception as e_stop:
                logger.warning(f"Error stopping sample query: {e_stop}", exc_info=True)
                return None

    if sample_data:
        logger.info("Sample records collected:")
        for idx, record in enumerate(sample_data, start=1):
            logger.info(f"Record {idx}: {record}")
    else:
        logger.info("No sample records collected (stream might be empty or processing timed out).")
    return sample_data


def _configure_spark_for_s3_parquet(spark):
    logger.info("Configuring Spark for S3 and Parquet writing...")
    spark.conf.set("spark.sql.shuffle.partitions", "1")  # Re-evaluate for production scale
    spark.conf.set("spark.sql.streaming.minBatchesToRetain", "1")
    spark.conf.set("spark.sql.parquet.compression.codec", "snappy")
    spark.conf.set("spark.sql.parquet.mergeSchema", "false")  # Global setting
    spark.conf.set("spark.sql.parquet.filterPushdown", "true")


def _write_stream_to_s3(df, out_path, chkpt_path, spark_session):
    logger.info(f"Preparing to write stream to S3: {out_path} (checkpoints at {chkpt_path})")

    _configure_spark_for_s3_parquet(spark_session)

    logger.info("Ensuring consistent data types for Parquet conversion...")
    # Ensure all expected columns are present and cast them
    # This is important to prevent schema evolution issues if a field is occasionally missing
    final_df = df.select(
        col("element").cast("string"),
        col("page").cast("string"),
        col("userAgent").cast("string"),
        col("timestamp").cast("string"),  # Original timestamp string
        col("ingest_ts").cast("string"),  # From JSON payload
        col("request_id").cast("string"),
        col("event_ts"),  # Derived timestamp type
        col("event_date")  # Derived date type
    )
    logger.info("Final DataFrame schema before S3 write:")
    final_df.printSchema()

    logger.info(f"Starting micro-batch processing to S3 at {time.time()}...")
    query = (
        final_df.writeStream
        .format("delta")
        .outputMode("append")
        .option("path", out_path)
        .option("checkpointLocation", chkpt_path)
        .option("mergeSchema", "true")  # Allow schema merging at the sink if necessary
        .partitionBy("event_date")
        .trigger(availableNow=True)
        .start()
    )
    logger.info(f"Streaming query started with ID {query.id}")

    logger.info("Waiting for streaming query to complete...")
    query.awaitTermination()
    logger.info("Streaming query completed.")


def check_data_post_processing(s3_bucket, s3_prefix, aws_region):
    s3_client = boto3.client('s3', region_name=aws_region)
    try:
        logger.info(f"Checking for output files in S3 bucket '{s3_bucket}' with prefix '{s3_prefix}'")
        response = s3_client.list_objects_v2(Bucket=s3_bucket, Prefix=s3_prefix)

        if 'Contents' in response and response['Contents']:
            logger.info(f"Found {len(response['Contents'])} output item(s) in S3 at '{s3_bucket}/{s3_prefix}'.")
            for item in response['Contents'][:5]:  # Log first 5 items
                logger.info(f"  - s3://{s3_bucket}/{item['Key']} (Size: {item['Size']} bytes)")
            if len(response['Contents']) > 5:
                logger.info(f"  ... and {len(response['Contents']) - 5} more items.")
        else:
            logger.warning(f"No output files found in S3 at '{s3_bucket}/{s3_prefix}'.")
    except Exception as exc:
        logger.error(f"Error checking for output files in S3: {exc}", exc_info=True)


def run_glue_job():
    job_args = _get_job_args()
    JOB_NAME = job_args["JOB_NAME"]
    STREAM_ARN = job_args["STREAM_ARN"]
    AWS_REGION = job_args["AWS_REGION"]
    ENVIRONMENT = job_args["ENVIRONMENT"]
    S3_BRONZE_BUCKET = job_args["S3_BRONZE_BUCKET"]

    # Schema Registry parameters
    REGISTRY_NAME = job_args["glue.schemaRegistry.registryName"]
    SCHEMA_NAME = job_args["glue.schemaRegistry.schemaName"]
    DATA_FORMAT = job_args["glue.schemaRegistry.dataFormat"]

    logger.info(f"Starting job {JOB_NAME} → stream {STREAM_ARN} using schema {REGISTRY_NAME}/{SCHEMA_NAME}")

    logger.info(f"Starting job {JOB_NAME} → stream {STREAM_ARN}")

    glue_context, spark_session = _initialize_spark_glue()
    input_schema = _define_input_schema()

    raw_kinesis_df = _read_from_kinesis_stream(
        glue_context,
        STREAM_ARN,
        AWS_REGION,
        REGISTRY_NAME,
        SCHEMA_NAME,
        DATA_FORMAT
    )

    if raw_kinesis_df is None or not raw_kinesis_df.columns:
        logger.warning("No data read from Kinesis or DataFrame is empty. Exiting job.")
        return

    transformed_df = _transform_data(raw_kinesis_df, input_schema)

    if transformed_df is None or not transformed_df.columns:
        logger.warning("Data transformation resulted in an empty DataFrame. Exiting job.")
        return

    # Collect sample data for logging/debugging (optional, can be removed in production)
    _collect_sample_data(transformed_df.limit(10))  # Limit input to sampling for performance

    s3_output_path = f"s3://{S3_BRONZE_BUCKET}/{ENVIRONMENT}/bronze/clicks/"
    s3_checkpoint_path = f"s3://{S3_BRONZE_BUCKET}/{ENVIRONMENT}/checkpoints/clicks/"

    _write_stream_to_s3(transformed_df, s3_output_path, s3_checkpoint_path, spark_session)

    # Post-processing check
    output_s3_prefix = f"{ENVIRONMENT}/bronze/clicks/"
    check_data_post_processing(S3_BRONZE_BUCKET, output_s3_prefix, AWS_REGION)

    logger.info(f"Job {JOB_NAME} completed successfully.")


if __name__ == "__main__":
    start = time.time()
    try:
        run_glue_job()
    except Exception as e:
        logger.error(f"Job failed with unhandled exception: {e}", exc_info=True)
        sys.exit(1)
    finally:
        elapsed = time.time() - start
        logger.info(f"Job runtime: {elapsed:.2f}s")
