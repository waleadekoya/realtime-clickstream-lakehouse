import os, json, boto3, time
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Kinesis client with proper error handling
try:
    kinesis = boto3.client("kinesis", region_name=os.environ["REGION"])
    STREAM = os.environ["STREAM_NAME"]
except KeyError as e:
    logger.error(f"Missing required environment variable: {e}")
    raise
except Exception as e:
    logger.error(f"Failed to initialize Kinesis client: {e}")
    raise

def lambda_handler(event, context):
    try:
        # event from API GW, body is JSON string
        logger.info(f"Received event: {event}")

        # Handle different event types (direct invocation vs. API Gateway)
        body = event.get("body", "{}")

        try:
            # Parse the JSON body
            parsed_body = json.loads(body)
        except json.JSONDecodeError as err:
            logger.error(f"Invalid JSON in request body: {err}")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid JSON in request body"})
            }

        # Add timestamp and request ID for traceability
        payload = {
            **parsed_body,
            "ingest_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": context.aws_request_id if context else "direct-invocation"
        }

        # Add basic validation
        if not payload.get("element"):
            logger.warning("No element specified in payload, using 'unknown'")

        # Send it to Kinesis with a more specific partition key strategy
        response = kinesis.put_record(
            StreamName=STREAM,
            PartitionKey=payload.get("element", "unknown"),
            Data=json.dumps(payload).encode("utf-8")
        )

        logger.info(f"Successfully sent record to Kinesis: {response}")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"  # CORS support
            },
            "body": json.dumps({
                "ingested": True,
                "shardId": response.get("ShardId"),
                "sequenceNumber": response.get("SequenceNumber")
            })
        }
    except Exception as exc:
        logger.error(f"Error processing event: {exc}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"  # CORS support
            },
            "body": json.dumps({
                "error": "Internal server error",
                "message": str(exc)
            })
        }
