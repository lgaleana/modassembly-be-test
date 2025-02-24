import argparse
import json
import os
import sys
from typing import Any, Dict
from dotenv import load_dotenv
from pydantic import ValidationError

load_dotenv()

from ai import llm
from utils.config.architecture import (
    Component,
    load_config,
    save_config,
)
from utils.files import File
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import (
    REPOS,
    extract_json,
    execute_git_commands,
    update_architecture_dependencies,
)


def run(app_name: str, user: str) -> Dict[str, Any]:
    from workflows.design import PROMPT

    config = load_config(app_name, user)

    conversation = Conversation()
    conversation.add_developer(PROMPT)
    raw_architecture = json.dumps(
        [c.model_dump() for c in config["architecture"]], indent=4
    )
    conversation.add_developer(f"Architecture and code:\n\n{raw_architecture}")

    file_to_component = {}
    for component in config["architecture"]:
        for file in component.files:
            file_to_component[file.path] = component
    components_that_changed = set()

    repo_name = f"{user}_{app_name}"
    repo_path = f"{REPOS}/{repo_name}/app"
    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".py") and not file.endswith("__init__.py"):
                relative_path = os.path.relpath(root, repo_path)
                if relative_path != ".":
                    relative_path = os.path.join("app", relative_path, file)
                else:
                    relative_path = f"app/{file}"

                full_path = os.path.join(root, file)
                with open(full_path, "r") as f:
                    code = f.read()

                target_file = None
                for file in file_to_component[relative_path].files:
                    if file.path == relative_path:
                        target_file = file
                        break
                assert target_file

                if target_file.content != code:
                    components_that_changed.add(
                        file_to_component[relative_path].design.key
                    )
                    target_file.content = code

    for component in config["architecture"]:
        if component.design.key not in components_that_changed:
            continue

        attempts = 0
        while True:
            attempts += 1
            try:
                conversation.add_user(
                    f"The code has changed for ::"
                    f"\n\n{component.model_dump()}\n\n"
                    "Update the component's specification. "
                    "Include every important detail. "
                    "Extract all the hardcoded values."
                )
                response = llm.stream_text(conversation)
                conversation.add_assistant(response)
                jsons = extract_json(response)
                assert len(jsons) == 1

                component.design = Component.model_validate(jsons[0])
                component.update_status = (
                    "up_to_date"
                    if component.update_status != "blocked"
                    else component.update_status
                )
                print_system(f"Updated :: {component.design.key}")
                break
            except ValidationError as e:
                if attempts == 3:
                    raise e
                conversation.add_system(f"{type(e).__name__}({e})")
                continue

    breakpoint()
    update_architecture_dependencies(config["architecture"])
    save_config(config)

    execute_git_commands(
        [
            ["git", "add", "."],
            ["git", "commit", "-m", "MANUAL: Synced architecture"],
            ["git", "push", "origin", "main"],
        ],
        repo=repo_name,
    )

    return config


if __name__ == "__main__":
    sys.path.append(os.path.expanduser("~/Code/modular/web/modassembly_web"))

    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    run(args.app, "lgaleana")
