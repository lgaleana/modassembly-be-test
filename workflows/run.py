import json
import os
import argparse
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()

from utils.files import File
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import (
    Component,
    REPOS,
    execute_deploy,
    group_nodes_by_dependencies,
    load_helpers,
    save_files,
)
from workflows.subworkflows import write_function


def run(app_name: str) -> str:
    with open(f"db/repos/{app_name}/config.json", "r") as f:
        architecture = {a["name"]: Component.model_validate(a) for a in json.load(f)}
    os.mkdir(f"db/repos/{app_name}/app")

    conversation = Conversation()
    conversation.add_user(
        f"Consider the following architecture of a python architecture: {architecture}"
    )

    main, helpers = load_helpers(architecture)
    for helper in [main, *helpers]:
        conversation.add_user(
            f"I wrote the code for:\n\n```python\n{helper.content}\n```"
        )
        conversation.add_user(f"I saved the code in {helper.path}.")

    nodes_to_parallelize = group_nodes_by_dependencies(list(architecture.values()))
    for level in nodes_to_parallelize:
        with ThreadPoolExecutor(max_workers=10) as executor:
            outputs = list(
                executor.map(
                    write_function, level, [conversation.copy() for _ in level]
                )
            )
        for output in outputs:
            conversation.add_user(output.user_message)
            conversation.add_assistant(output.assistant_message)

            file_path = f"app/components/{output.component}.py"
            os.makedirs(
                os.path.dirname(f"{REPOS}/{app_name}/{file_path}"), exist_ok=True
            )
            conversation.add_user(f"I saved the code in {file_path}.")
            with open(f"{REPOS}/{app_name}/{file_path}", "w") as f:
                f.write(output.code)
            architecture[output.component].file = File(
                path=file_path, content=output.code
            )

    save_files(app_name, main, helpers, architecture=architecture)

    service_url = execute_deploy(app_name)
    print_system(service_url)
    return service_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    run(args.app)
