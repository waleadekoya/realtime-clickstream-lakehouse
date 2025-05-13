import boto3
import json
import logging
import os
import time
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Kinesis client with proper error handling
try:
    REGION = os.environ.get('REGION')
    kinesis = boto3.client("kinesis", region_name=REGION)
    STREAM = os.environ["STREAM_NAME"]
except KeyError as e:
    logger.error(f"Missing required environment variable: {e}")
    raise
except Exception as e:
    logger.error(f"Failed to initialize Kinesis client: {e}")
    raise

glue_client = boto3.client('glue', region_name=REGION)
REGISTRY_NAME = os.environ.get('REGISTRY_NAME')
SCHEMA_NAME = os.environ.get('SCHEMA_NAME')

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

        # ----- SCHEMA VALIDATION WITH GLUE SCHEMA REGISTRY -----
        # Only perform validation if registry configuration is available
        logger.info(f"Schema Registry Config - Registry: {REGISTRY_NAME}, Schema: {SCHEMA_NAME}, Region: {REGION}")

        try:
        # Try to connect to the schema registry
            resp = glue_client.get_schema_version(
                SchemaId={
                    'RegistryName': REGISTRY_NAME,
                    'SchemaName': SCHEMA_NAME
                },
                SchemaVersionNumber={'LatestVersion': True}
            )
            logger.info(f"Successfully connected to schema registry: {resp}")
        except Exception as err:
            logger.error(f"Error connecting to schema registry: {str(err)}")
            return None


        if REGISTRY_NAME and SCHEMA_NAME:
            try:
                logger.info(f"Validating against schema {REGISTRY_NAME}/{SCHEMA_NAME}")

                # First, get the schema definition
                schema_response = glue_client.get_schema_version(
                    SchemaId={
                        'RegistryName': REGISTRY_NAME,
                        'SchemaName': SCHEMA_NAME
                    },
                    SchemaVersionNumber={'LatestVersion': True}
                )

                # Extract the schema definition
                schema_definition = schema_response.get('SchemaDefinition')



                # Check validation result
                if not schema_definition:
                    logger.error("Failed to get schema definition")
                    return {
                        "statusCode": 500,
                        "headers": {
                            "Content-Type": "application/json",
                            "Access-Control-Allow-Origin": "*"
                        },
                        "body": json.dumps({
                            "error": "Schema validation error",
                            "details": "Failed to retrieve schema definition"
                        })
                    }


                # Convert payload to JSON string for validation
                payload_json = json.dumps(payload)
                schema = json.loads(schema_definition)
                logger.info(f"Schema validation passed. Schema: {schema}")
            except ClientError as err:
                error_code = err.response.get('Error', {}).get('Code', '')
                # Log error but continue - let Glue validate on the consumer side
                logger.warning(f"Schema validation error (code: {error_code}): {str(err)}")

                # If it's a critical error like missing schema, Fail
                if error_code in ['ResourceNotFoundException', 'AccessDeniedException']:
                    return {
                        "statusCode": 500,
                        "headers": {
                            "Content-Type": "application/json",
                            "Access-Control-Allow-Origin": "*"
                        },
                        "body": json.dumps({
                            "error": "Schema validation configuration error",
                            "details": str(err)
                        })
                    }
        else:
            logger.warning("Schema Registry configuration not found, skipping validation")


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
