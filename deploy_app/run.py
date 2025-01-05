import argparse
import os
import subprocess

from utils.files import REPOS
from utils.io import print_system


def execute_deploy(app_name: str) -> str:
    print_system("Deploying application...")
    original_dir = os.getcwd()
    try:
        os.chdir(f"{REPOS}/{app_name}")
        subprocess.run(["chmod", "+x", "deploy.sh"], check=True)
        output = subprocess.run(
            ["./deploy.sh", app_name], check=True, capture_output=True, text=True
        )
        print_system(output.stdout)
        print_system(output.stderr)
        return output.stdout.splitlines()[-1]
    finally:
        os.chdir(original_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    execute_deploy(args.app)
