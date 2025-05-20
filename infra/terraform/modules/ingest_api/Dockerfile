FROM public.ecr.aws/lambda/python:3.12 as build

# Install the schema registry package and its dependencies
RUN pip install --no-compile --no-cache-dir aws-glue-schema-registry==1.1.3 -t /opt/python

# Create the runtime image
FROM public.ecr.aws/lambda/python:3.12

# Copy dependencies from build stage
COPY --from=build /opt/python /opt/python

# Add Lambda handler code
COPY tmp/click_handler.py ${LAMBDA_TASK_ROOT}/

# Set environment variables (these will be overridden by Lambda config)
ENV REGION=us-east-1
ENV STREAM_NAME=placeholder
ENV REGISTRY_NAME=placeholder
ENV SCHEMA_NAME=placeholder

# Set the handler
CMD [ "click_handler.lambda_handler" ]
