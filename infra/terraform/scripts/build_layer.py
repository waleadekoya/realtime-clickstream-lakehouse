#!/usr/bin/env python3
"""
Lambda Layer Builder Script for AWS Glue Schema Registry

This script builds a Lambda layer containing the AWS Glue Schema Registry client
and its dependencies. It can build the layer in two ways:

1. Using Docker (preferred): Builds the layer in a container using the official
   AWS Lambda Python 3.12 runtime image. This ensures binary compatibility with
   the Lambda environment, which is critical for packages with C extensions like
   orjson.

2. Locally (fallback): Builds the layer on the local machine. This may result in
   compatibility issues if the local environment differs from the Lambda runtime
   environment (e.g., Windows vs. Linux).

The script automatically detects if Docker is available and uses it if possible.
"""
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

logger = logging.getLogger()
logger.setLevel(logging.INFO)
## ── configure root logger to write INFO+ messages to stdout ──────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(lineno)d:  %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

def start_docker_daemon():
    """
    Attempt to start the Docker daemon if it's installed but not running.

    This function tries to start Docker using platform-specific commands.
    It handles Windows, macOS, and Linux differently.

    Returns:
        bool: True if Docker was successfully started, False otherwise.
    """
    system = platform.system()
    try:
        if system == "Windows":
            # On Windows, try to start Docker Desktop
            logger.info("Attempting to start Docker Desktop on Windows...")
            # Check if Docker Desktop is installed
            docker_desktop_path = os.path.expandvars(r"%ProgramFiles%\Docker\Docker\Docker Desktop.exe")
            if not os.path.exists(docker_desktop_path):
                docker_desktop_path = os.path.expandvars(r"%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe")

            if os.path.exists(docker_desktop_path):
                # Start Docker Desktop
                subprocess.Popen([docker_desktop_path], 
                                 stdout=subprocess.PIPE, 
                                 stderr=subprocess.PIPE)
                logger.info("Docker Desktop is starting. This may take a moment...")

                # Wait for Docker to start (up to 60 seconds)
                for _ in range(12):  # 12 * 5 seconds = 60 seconds
                    time.sleep(5)
                    try:
                        subprocess.run(["docker", "info"], 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.PIPE, 
                                      check=True)
                        logger.info("Docker Desktop has started successfully.")
                        return True
                    except subprocess.CalledProcessError:
                        logger.error("Waiting for Docker Desktop to start...")

                logger.info("Timed out waiting for Docker Desktop to start.")
                return False
            else:
                logger.info("Docker Desktop executable not found.")
                return False

        elif system == "Darwin":  # macOS
            # On macOS, try to start Docker Desktop
            logger.info("Attempting to start Docker Desktop on macOS...")
            try:
                subprocess.run(["open", "-a", "Docker"], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              check=True)

                # Wait for Docker to start (up to 60 seconds)
                for _ in range(12):  # 12 * 5 seconds = 60 seconds
                    time.sleep(5)
                    try:
                        subprocess.run(["docker", "info"], 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.PIPE, 
                                      check=True)
                        logger.info("Docker Desktop has started successfully.")
                        return True
                    except subprocess.CalledProcessError:
                        logger.info("Waiting for Docker Desktop to start...")

                logger.info("Timed out waiting for Docker Desktop to start.")
                return False
            except subprocess.CalledProcessError:
                logger.error("Failed to start Docker Desktop on macOS.")
                return False

        elif system == "Linux":
            # On Linux, try to start the Docker daemon using systemctl
            logger.info("Attempting to start Docker daemon on Linux...")
            try:
                # Check if user has permission to start Docker service
                result = subprocess.run(["systemctl", "status", "docker"], 
                                       stdout=subprocess.PIPE, 
                                       stderr=subprocess.PIPE)

                if result.returncode == 0 or result.returncode == 3:  # 3 means service is stopped
                    # Try to start Docker service
                    try:
                        subprocess.run(["sudo", "systemctl", "start", "docker"], 
                                      stdout=subprocess.PIPE, 
                                      stderr=subprocess.PIPE, 
                                      check=True)

                        # Wait for Docker to start (up to 30 seconds)
                        for _ in range(6):  # 6 * 5 seconds = 30 seconds
                            time.sleep(5)
                            try:
                                subprocess.run(["docker", "info"], 
                                              stdout=subprocess.PIPE, 
                                              stderr=subprocess.PIPE, 
                                              check=True)
                                logger.info("Docker daemon has started successfully.")
                                return True
                            except subprocess.CalledProcessError:
                                logger.info("Waiting for Docker daemon to start...")

                        logger.info("Timed out waiting for Docker daemon to start.")
                        return False
                    except subprocess.CalledProcessError:
                        logger.error("Failed to start Docker daemon. You may need to run this script with sudo privileges.")
                        return False
                else:
                    logger.info("Docker service not found or user doesn't have permission to access it.")
                    return False
            except FileNotFoundError:
                # systemctl not available, try service command
                try:
                    subprocess.run(["sudo", "service", "docker", "start"], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE, 
                                  check=True)

                    # Wait for Docker to start (up to 30 seconds)
                    for _ in range(6):  # 6 * 5 seconds = 30 seconds
                        time.sleep(5)
                        try:
                            subprocess.run(["docker", "info"], 
                                          stdout=subprocess.PIPE, 
                                          stderr=subprocess.PIPE, 
                                          check=True)
                            logger.info("Docker daemon has started successfully.")
                            return True
                        except subprocess.CalledProcessError:
                            logger.info("Waiting for Docker daemon to start...")

                    logger.info("Timed out waiting for Docker daemon to start.")
                    return False
                except subprocess.CalledProcessError:
                    logger.info("Failed to start Docker daemon using service command.")
                    return False
                except FileNotFoundError:
                    logger.error("Neither systemctl nor service commands are available.")
                    return False
        else:
            logger.info(f"Unsupported operating system: {system}")
            return False
    except Exception as e:
        logger.error(f"Error attempting to start Docker: {str(e)}")
        return False

def is_docker_available():
    """
    Check if Docker is available and running on the system.

    This function attempts to run 'docker info' to determine if Docker
    is installed, accessible, and the Docker daemon is running. Docker is required 
    for building Lambda layers with binary compatibility to the Lambda runtime environment.
    If Docker is installed but not running, it will attempt to start it.

    Returns:
        bool: True if Docker is available and running, False otherwise.
    """
    try:
        # Run docker info to check if Docker daemon is running
        subprocess.run(
            ["docker", "info"], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            check=True
        )
        logger.info("Docker is available and running. Will use Docker to build the Lambda layer.")
        return True
    except subprocess.CalledProcessError as err:
        # This error typically occurs when Docker is installed but the daemon is not running
        logger.info(f"ERROR: {err.stderr.decode('utf-8').strip()}")
        logger.info("Docker is installed but the daemon is not running. Attempting to start Docker...")

        # Try to start Docker
        if start_docker_daemon():
            logger.info("Docker has been started successfully. Will use Docker to build the Lambda layer.")
            return True
        else:
            logger.info("Failed to start Docker. Will fall back to local build method.")
            return False
    except FileNotFoundError:
        # This error occurs when Docker is not installed
        logger.error("Docker is not installed. Will fall back to local build method.")
        return False
    except Exception as err:
        # Catch any other unexpected errors
        logger.error(f"Unexpected error checking Docker availability: {str(err)}")
        logger.info("Will fall back to local build method.")
        return False

def build_layer_with_docker(temp_dir, output_path, python_packages_dir):
    """
    Build the Lambda layer using Docker with the AWS Lambda Python runtime.

    This function creates a Dockerfile that uses the official AWS Lambda Python 3.12
    runtime as a base image, installs the required packages, and copies the layer
    files to the local filesystem. This ensures that binary dependencies like orjson
    are compiled in an environment that matches the Lambda runtime environment.

    Args:
        temp_dir (str): Path to the temporary directory for building the layer
        output_path (str): Path where the final layer ZIP file will be saved
        python_packages_dir (str): Path to the directory where Python packages will be installed

    Returns:
        bool: True if the build was successful, False otherwise
    """
    logger.info("Building Lambda layer using Docker with AWS Lambda Python 3.12 runtime...")

    try:
        # Create a Dockerfile in the temp directory
        dockerfile_path = os.path.join(temp_dir, "Dockerfile")
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write("""
# Stage 1: build on AWS Lambda Python 3.12 runtime
FROM public.ecr.aws/sam/build-python3.12 AS builder

# Install packages with specific versions to ensure compatibility
RUN pip3 install --no-cache-dir \
      aws-glue-schema-registry==1.1.3 \
      boto3>=1.17.102 \
      fastavro>=1.4.5 \
      fastjsonschema~=2.15 \
      orjson==3.10.18 \
      --target /opt/python

# Create the orjson.orjson module if it doesn't exist
RUN mkdir -p /opt/python/orjson/orjson && \
    echo "from orjson import dumps, loads" > /opt/python/orjson/orjson/__init__.py

# Stage 2: assemble layer zip
FROM scratch AS layer
COPY --from=builder /opt/python /layer/python

CMD ["true"]
""")

        # Build the Docker image from the Dockerfile
        try:
            subprocess.run(
                ["docker", "build", "-t", "lambda-layer-builder", temp_dir],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Error building Docker image: {e.stderr.decode('utf-8').strip()}")
            logger.info("Falling back to local build method...")
            return False

        # Create a container from the image and copy the layer files
        try:
            container_id = subprocess.check_output(
                ["docker", "create", "lambda-layer-builder"],
                stderr=subprocess.PIPE,
                universal_newlines=True
            ).strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Error creating Docker container: {e.stderr.strip()}")
            logger.info("Falling back to local build method...")
            return False

        try:
            # Copy the layer files from the container to the temp directory
            subprocess.run(
                ["docker", "cp", f"{container_id}:/layer/python/.", python_packages_dir],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            logger.info(f"Successfully copied layer files from Docker container to {python_packages_dir}")

            # List the contents of the python directory for verification
            logger.info(f"Contents of {python_packages_dir}: {os.listdir(python_packages_dir)}")

            # Create the zip file
            if os.path.exists(output_path):
                os.remove(output_path)

            shutil.make_archive(
                output_path[:-4],  # Remove .zip extension
                "zip",
                temp_dir
            )

            logger.info(f"Lambda layer created at: {output_path}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error copying files from Docker container: {e.stderr.decode('utf-8').strip() if hasattr(e, 'stderr') else str(e)}")
            logger.info("Falling back to local build method...")
            return False
        finally:
            # Clean up the container
            try:
                subprocess.run(
                    ["docker", "rm", container_id],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True
                )
            except subprocess.CalledProcessError as e:
                logger.erorr(f"Warning: Failed to remove Docker container {container_id}: {e.stderr.decode('utf-8').strip() if hasattr(e, 'stderr') else str(e)}")
    except Exception as err:
        logger.error(f"Unexpected error during Docker build: {str(err)}")
        logger.info("Falling back to local build method...")
        return False

def build_layer_locally(temp_dir, output_path, python_packages_dir):
    """
    Build the Lambda layer locally using pip.

    This function attempts to install the required packages using the local
    Python environment. This is a fallback method when Docker is not available.
    Note that this method may result in compatibility issues if the local
    environment differs from the Lambda runtime environment, especially for
    packages with binary dependencies like orjson.

    Args:
        temp_dir (str): Path to the temporary directory for building the layer
        output_path (str): Path where the final layer ZIP file will be saved
        python_packages_dir (str): Path to the directory where Python packages will be installed

    Returns:
        bool: True if the build was successful, False otherwise
    """
    logger.info("Building Lambda layer locally...")

    # Print the directory structure for debugging
    logger.info(f"Using Python packages directory at: {python_packages_dir}")

    # Check if pip module is available in the current Python environment
    pip_available = False
    try:
        import importlib.util
        pip_spec = importlib.util.find_spec("pip")
        pip_available = pip_spec is not None
    except ImportError:
        pip_available = False

    success = False

    # Try different methods to install packages to handle various environments
    if pip_available:
        try:
            # First, try using pip as a module (standard approach)
            logger.info("Attempting to install packages using Python's pip module...")
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "aws-glue-schema-registry==1.1.3",  # Main package for schema registry with specific version
                "boto3>=1.17.102",  # Required dependency
                "fastavro>=1.4.5",  # Required dependency
                "fastjsonschema~=2.15",  # Required dependency
                "orjson==3.10.18",  # Required dependency with specific version
                "--no-cache-dir",  # Ensure a clean installation
                "--target", python_packages_dir
            ])
            success = True
            logger.info("Successfully installed packages using Python's pip module.")
        except subprocess.CalledProcessError as e:
            logger.error(f"First pip install attempt failed: {e}")
    else:
        logger.info("Python's pip module not available in the current environment.")

    # If first method failed, try using pip directly
    if not success:
        try:
            # Determine pip command based on platform
            pip_cmd = "pip3" if sys.platform != "win32" else "pip"
            logger.info(f"Attempting to install packages using {pip_cmd} command...")
            subprocess.check_call([
                pip_cmd, "install",
                "aws-glue-schema-registry==1.1.3",  # Main package for schema registry with specific version
                "boto3>=1.17.102",  # Required dependency
                "fastavro>=1.4.5",  # Required dependency
                "fastjsonschema~=2.15",  # Required dependency
                "orjson==3.10.18",  # Required dependency with specific version
                "--no-cache-dir",  # Ensure a clean installation
                "--target", python_packages_dir
            ])
            success = True
            logger.info(f"Successfully installed packages using {pip_cmd} command.")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.info(f"Second pip install attempt failed: {e}")

    # As a last resort, try using python/python3 with -m pip
    if not success:
        try:
            # Use platform-specific Python command
            python_cmd = "python3" if sys.platform != "win32" else "python"
            logger.info(f"Attempting to install packages using {python_cmd} -m pip...")
            subprocess.check_call([
                python_cmd, "-m", "pip", "install",
                "aws-glue-schema-registry==1.1.3",  # Main package for schema registry with specific version
                "boto3>=1.17.102",  # Required dependency
                "fastavro>=1.4.5",  # Required dependency
                "fastjsonschema~=2.15",  # Required dependency
                "orjson==3.10.18",  # Required dependency with specific version
                "--no-cache-dir",  # Ensure a clean installation
                "--target", python_packages_dir
            ])
            success = True
            logger.info(f"Successfully installed packages using {python_cmd} -m pip.")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.error(f"Third pip install attempt failed: {e}")
            raise Exception("All package installation methods failed. Please ensure pip is installed and accessible.")

    # Create the orjson.orjson module if it doesn't exist
    if success:
        try:
            # Create the directory structure
            orjson_orjson_dir = os.path.join(python_packages_dir, "orjson", "orjson")
            os.makedirs(orjson_orjson_dir, exist_ok=True)

            # Create the __init__.py file
            init_file = os.path.join(orjson_orjson_dir, "__init__.py")
            with open(init_file, "w", encoding="utf-8") as f:
                f.write("from orjson import dumps, loads\n")

            logger.info(f"Created orjson.orjson module at {orjson_orjson_dir}")
        except Exception as e:
            logger.error(f"Error creating orjson.orjson module: {e}")
            # Don't fail the build if this step fails

    return success

def build_schema_registry_layer(output_dir):
    """
    Build a schema registry layer with required AWS libraries.

    This is the main function that orchestrates the layer building process.
    It creates a temporary directory, checks if Docker is available, and then
    calls either build_layer_with_docker or build_layer_locally to build the layer.
    It also verifies that the required packages were installed correctly.

    Args:
        output_dir (str): Directory where the final layer ZIP file will be saved

    Returns:
        str: Path to the created layer ZIP file
    """

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "schema-registry-layer.zip")

    # Create the layer
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the layer structure for Python Lambda layers
        # Lambda expects packages to be in the 'python' directory
        python_packages_dir = os.path.join(temp_dir, "python")
        os.makedirs(python_packages_dir, exist_ok=True)

        # Check if Docker is available
        docker_available = is_docker_available()

        if docker_available:
            # Build the layer using Docker (preferred method for binary compatibility)
            docker_success = build_layer_with_docker(temp_dir, output_path, python_packages_dir)
            if not docker_success:
                logger.info("Docker build failed. Falling back to local build method.")
                logger.info("WARNING: Building on a non-Linux platform may result in compatibility issues with Lambda.")
                # Build the layer locally as a fallback
                success = build_layer_locally(temp_dir, output_path, python_packages_dir)
            else:
                success = True
        else:
            logger.info("Docker is not available. Falling back to local build method.")
            logger.info("WARNING: Building on a non-Linux platform may result in compatibility issues with Lambda.")
            # Build the layer locally
            success = build_layer_locally(temp_dir, output_path, python_packages_dir)

        # Verify that the aws_glue_schema_registry package was installed correctly
        try:
            # List all installed packages for debugging
            logger.info("Listing installed packages in the layer:")
            installed_packages = os.listdir(python_packages_dir)
            logger.info(f"Packages in {python_packages_dir}: {installed_packages}")

            # Check specifically for aws_glue_schema_registry
            if any(p.startswith("aws_glue_schema_registry-") for p in installed_packages) \
                    or "aws_schema_registry" in installed_packages:
                logger.info("✅ Schema Registry client is present")
            else:
                logger.info("❌ Schema Registry client missing from layer!")
                # It might be inside another package, so check subdirectories
                for pkg in installed_packages:
                    pkg_path = os.path.join(python_packages_dir, pkg)
                    if os.path.isdir(pkg_path) and "aws_glue_schema_registry" in os.listdir(pkg_path):
                        logger.info(f"aws_glue_schema_registry found inside {pkg}")
        except Exception as err:
            logger.error(f"Error verifying installed packages: {err}")

        # Create a zip file (overwrite if it exists)
        if os.path.exists(output_path):
            os.remove(output_path)

        shutil.make_archive(
            output_path[:-4],  # Remove .zip extension
            "zip",
            temp_dir
        )

        logger.info(f"Lambda layer created at: {output_path}")
        return output_path

if __name__ == "__main__":
    # Get the project root (4 levels up from the script)
    project_root = Path(__file__).resolve().parents[3]
    layer_dir = project_root / "etl" / "layer_packages"

    try:
        build_schema_registry_layer(layer_dir.as_posix())
    except Exception as e:
        logger.error(f"Error creating lambda layer: {e}")
        sys.exit(1)
