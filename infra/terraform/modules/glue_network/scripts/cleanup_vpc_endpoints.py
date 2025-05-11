import subprocess
import time
import json
import sys
import argparse

def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.stdout.strip(), result.returncode
    except Exception as e:
        print(f"Error executing command: {e}")
        return "", 1

def cleanup_vpc_endpoint(endpoint_id, region):
    print(f"Processing VPC endpoint: {endpoint_id}")

    # First, attempt to delete the endpoint directly
    print("Attempting to delete VPC endpoint...")
    run_command(["aws", "ec2", "delete-vpc-endpoints", "--region", region, "--vpc-endpoint-ids", endpoint_id])

    # Wait a bit for deletion to take effect
    time.sleep(20)

    # Check if the endpoint is still around
    output, _ = run_command(["aws", "ec2", "describe-vpc-endpoints", "--region", region, "--vpc-endpoint-ids", endpoint_id])
    endpoint_exists = len(output) > 0 and "VpcEndpoints" in output

    if endpoint_exists:
        try:
            endpoint_json = json.loads(output)
            if endpoint_json.get("VpcEndpoints", []):
                endpoint_state = endpoint_json["VpcEndpoints"][0].get("State", "unknown")
                print(f"VPC Endpoint still exists, state: {endpoint_state}")

                # Find ENIs associated with this endpoint
                eni_output, _ = run_command(["aws", "ec2", "describe-network-interfaces",
                                             "--region", region,
                                             "--filters", f"Name=vpc-endpoint-id,Values={endpoint_id}"])

                if "NetworkInterfaces" in eni_output:
                    eni_json = json.loads(eni_output)
                    enis = [ni.get("NetworkInterfaceId") for ni in eni_json.get("NetworkInterfaces", [])]

                    if enis:
                        print(f"Found ENIs associated with VPC endpoint: {', '.join(enis)}")

                        for eni_id in enis:
                            print(f"Working on ENI {eni_id}")

                            # Check for attachment
                            attachment_output, _ = run_command(["aws", "ec2", "describe-network-interfaces",
                                                                "--region", region,
                                                                "--network-interface-ids", eni_id])

                            if "NetworkInterfaces" in attachment_output:
                                attachment_json = json.loads(attachment_output)
                                if attachment_json.get("NetworkInterfaces"):
                                    attachment = attachment_json["NetworkInterfaces"][0].get("Attachment", {})
                                    attachment_id = attachment.get("AttachmentId")

                                    if attachment_id:
                                        print(f"Detaching ENI {eni_id} (attachment: {attachment_id})")
                                        run_command(["aws", "ec2", "detach-network-interface",
                                                     "--region", region,
                                                     "--attachment-id", attachment_id,
                                                     "--force"])
                                        time.sleep(10)  # Wait for detachment

                            # Try to delete the ENI
                            print(f"Attempting to delete ENI {eni_id}")
                            run_command(["aws", "ec2", "delete-network-interface",
                                         "--region", region,
                                         "--network-interface-id", eni_id])

                # Try one more time to delete the endpoint
                print("Retrying deletion of VPC endpoint...")
                run_command(["aws", "ec2", "delete-vpc-endpoints",
                             "--region", region,
                             "--vpc-endpoint-ids", endpoint_id])
        except json.JSONDecodeError:
            print(f"Error parsing endpoint JSON response: {output}")
    else:
        print("VPC Endpoint successfully deleted or already gone")

def main():
    parser = argparse.ArgumentParser(description='Clean up VPC endpoints')
    parser.add_argument('--region', required=True, help='AWS region')
    parser.add_argument('--endpoints', required=True, help='Comma-separated list of endpoint IDs')

    args = parser.parse_args()
    region = args.region
    endpoints = args.endpoints.split(',')

    print("Ensuring proper cleanup of all VPC endpoints")
    for endpoint_id in endpoints:
        if endpoint_id.strip():  # Skip empty entries
            cleanup_vpc_endpoint(endpoint_id.strip(), region)

if __name__ == "__main__":
    main()
