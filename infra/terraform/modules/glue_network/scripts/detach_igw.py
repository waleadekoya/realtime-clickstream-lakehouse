# infra/terraform/modules/glue_network/scripts/detach_igw.py

import subprocess
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description='Detach Internet Gateway from VPC')
    parser.add_argument('--region', required=True, help='AWS region')
    parser.add_argument('--igw-id', required=True, help='Internet Gateway ID')
    parser.add_argument('--vpc-id', required=True, help='VPC ID')

    args = parser.parse_args()

    print(f"Detaching Internet Gateway {args.igw_id} from VPC {args.vpc_id}")
    try:
        subprocess.run(["aws", "ec2", "detach-internet-gateway",
                        "--internet-gateway-id", args.igw_id,
                        "--vpc-id", args.vpc_id,
                        "--region", args.region],
                       check=False)
    except Exception as e:
        print(f"Error during detachment (can be ignored if already detached): {e}")

if __name__ == "__main__":
    main()
