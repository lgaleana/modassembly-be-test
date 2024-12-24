import json
import os
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()

from utils.files import File
from utils.io import print_system
from utils.state import Conversation
from utils.static_analysis import extract_router_name
from workflows.helpers import (
    Component,
    REPOS,
    execute_deploy,
    group_nodes_by_dependencies,
)
from workflows.subworkflows import save_files, write_function


def run(app_name: str) -> str:
    with open(f"db/repos/{app_name}/config.json", "r") as f:
        architecture = {a["name"]: Component.model_validate(a) for a in json.load(f)}
    os.mkdir(f"{REPOS}/{app_name}/app")
    with open(f"{REPOS}/{app_name}/app/__init__.py", "w") as f:
        f.write("")

    conversation = Conversation()
    conversation.add_user(
        f"Consider the following architecture of a python architecture: {architecture}"
    )

    save_files(app_name, architecture, conversation)

    nodes_to_parallelize = group_nodes_by_dependencies(list(architecture.values()))
    os.makedirs(f"{REPOS}/{app_name}/app/components", exist_ok=True)
    with open(f"{REPOS}/{app_name}/app/components/__init__.py", "w") as f:
        f.write("")
    for level in nodes_to_parallelize:
        with ThreadPoolExecutor(max_workers=10) as executor:
            outputs = list(
                executor.map(
                    write_function,
                    [app_name] * len(level),
                    level,
                    [conversation.copy() for _ in level],
                )
            )
        for output in outputs:
            conversation.add_user(output.user_message)
            conversation.add_assistant(output.assistant_message)
            conversation.add_user(f"I saved the code in {output.file.path}.")
            architecture[output.component].file = output.file

    with open(f"{REPOS}/{app_name}/app/main.py", "r") as f:
        main_content = f.read()
    main_content += "\n"
    for component in architecture.values():
        if component.is_api:
            assert component.file
            module = component.file.path.replace(".py", "").replace("/", ".")
            router_name = extract_router_name(component.file)
            main_content += f"from {module} import {router_name}\n"
            main_content += f"app.include_router({router_name})\n"
    with open(f"{REPOS}/{app_name}/app/main.py", "w") as f:
        f.write(main_content)

    service_url = execute_deploy(app_name)
    print_system(service_url)
    return service_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    run(args.app)
