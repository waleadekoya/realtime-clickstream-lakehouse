import json
import logging
import os
import sys
import time

import boto3

# Set up a more detailed logger
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

# Add Lambda layer paths to sys.path to ensure modules can be found
# Lambda layers are mounted at /opt in the Lambda runtime
if os.path.exists('/opt/python'):
    sys.path.insert(0, '/opt/python')
    logger.info("Added /opt/python to sys.path")

    # Handle orjson import issue - ensure orjson is properly available
    try:
        import orjson
        import importlib.abc
        import importlib.machinery

        # Create a more robust solution using Python's import system
        # This approach creates a custom finder and loader for the orjson.orjson module

        class OrjsonLoader(importlib.abc.Loader):
            """Custom loader for orjson.orjson that returns the orjson module itself."""

            @staticmethod
            def create_module(spec):
                """Return None to use the default module creation."""
                return None

            @staticmethod
            def exec_module(module):
                """Execute the module by copying all attributes from orjson."""
                # Copy all attributes from orjson to the new module
                for attr_name in dir(orjson):
                    if not attr_name.startswith('__'):
                        setattr(module, attr_name, getattr(orjson, attr_name))

                # Explicitly set dumps and loads functions
                module.dumps = orjson.dumps
                module.loads = orjson.loads

                # Log success for debugging
                logger.info(f"Successfully initialized orjson.orjson module")

        class OrjsonFinder(importlib.abc.MetaPathFinder):
            """Custom finder for orjson.orjson that returns our custom loader."""

            @staticmethod
            def find_spec(fullname, path, target=None):
                """Find the orjson.orjson module and return a spec with our custom loader."""
                if fullname == 'orjson.orjson':
                    # Create a ModuleSpec with our custom loader
                    return importlib.machinery.ModuleSpec(
                        name=fullname,
                        loader=OrjsonLoader(),
                        is_package=False
                    )
                return None

        # Register our custom finder at the beginning of sys.meta_path
        # This ensures it's checked before the default finders
        sys.meta_path.insert(0, OrjsonFinder())

        # Also set up the orjson.orjson module directly in sys.modules as a fallback
        # This handles the case where code directly accesses sys.modules
        if 'orjson.orjson' not in sys.modules:
            # Create a new module object
            import types
            orjson_orjson_module = types.ModuleType('orjson.orjson')

            # Copy all attributes from orjson
            for attr_name in dir(orjson):
                if not attr_name.startswith('__'):
                    setattr(orjson_orjson_module, attr_name, getattr(orjson, attr_name))

            # Explicitly set dumps and loads functions
            orjson_orjson_module.dumps = orjson.dumps
            orjson_orjson_module.loads = orjson.loads

            # Add the module to sys.modules
            sys.modules['orjson.orjson'] = orjson_orjson_module

        # Test the import to verify it works
        try:
            # Try both import styles to ensure they work
            import orjson.orjson
            from orjson.orjson import dumps, loads

            # Verify the functions work as expected
            test_data = {"test": "data"}
            encoded = dumps(test_data)
            decoded = loads(encoded)
            assert decoded == test_data, "Serialization/deserialization test failed"

            # Verify that orjson.orjson is properly set up
            logger.info(f"Verification: Successfully imported and tested orjson.orjson")
            logger.info(f"orjson module ID: {id(orjson)}")
            logger.info(f"orjson.orjson module ID: {id(orjson.orjson)}")
            logger.info(f"orjson.dumps == orjson.orjson.dumps: {orjson.dumps is orjson.orjson.dumps}")
        except (ImportError, AssertionError) as e:
            logger.error(f"Verification failed: Could not import or use orjson.orjson after setup: {e}")
            # Don't raise, continue with the import attempt

        logger.info("Successfully set up orjson.orjson module")
    except ImportError as e:
        logger.error(f"Failed to import orjson: {e}")
        # Continue anyway, as the schema registry import might still work

# Schema validation has been removed and deferred to the Glue ETL job
# This simplifies the Lambda function and reduces dependencies


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
        # Schema validation is now deferred to the Glue ETL job
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
