import argparse
import json
import os
import sys

from dotenv import load_dotenv
from pydantic import ValidationError

load_dotenv()

from ai import llm
from utils.config.architecture import (
    Component,
    ImplementedComponent,
    Infrastructure,
    load_config,
    save_config,
)
from utils.files import File
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import (
    REPOS,
    extract_json,
    update_architecture_dependencies,
    update_main,
)
from workflows.subworkflows import save_templates


def sync_configs(app_name: str, user: str) -> None:
    from workflows.design import PROMPT

    config = load_config(app_name, user)
    architecture = {c.design.key: c for c in config["architecture"]}

    conversation = Conversation()
    conversation.add_system(PROMPT)
    raw_architecture = json.dumps(
        [c.model_dump() for c in config["architecture"]], indent=4
    )
    conversation.add_user(f"Architecture and code:\n\n{raw_architecture}")

    repo_name = f"{user}_{app_name}"
    repo_path = f"{REPOS}/{repo_name}/app"
    synced_architecture = [
        component
        for component in config["architecture"]
        if isinstance(component.design.root, Infrastructure)
    ]
    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".py") and not file.endswith("__init__.py"):
                relative_path = os.path.relpath(root, repo_path)
                key = file.replace(".py", "")
                if relative_path != ".":
                    key = os.path.join(relative_path, key)
                    key = key.replace(os.sep, ".")
                key = f"app.{key}"

                full_path = os.path.join(root, file)
                with open(full_path, "r") as f:
                    code = f.read()

                attempts = 0
                while True:
                    attempts += 1
                    design_component = None
                    try:
                        if key in architecture:
                            assert architecture[key].file
                            old_component = architecture[key]
                            if old_component.file.content != code:
                                conversation.add_user(
                                    f"The code for :: {key} has changed. "
                                    f"New code ::\n\n{code}\n\n"
                                    "Update the component's spec. "
                                    "Include every important detail. "
                                    "Ignore logs and comments. "
                                    "Very important: Extract all the hardcoded values "
                                    'and add them to "purpose".'
                                )
                                response = llm.stream_text(conversation)
                                conversation.add_assistant(response)
                                jsons = extract_json(response)
                                assert len(jsons) == 1
                                design_component = Component.model_validate(jsons[0])
                                print_system(f"Updated :: {key}")
                            else:
                                design_component = old_component.design

                            synced_architecture.append(
                                ImplementedComponent(
                                    design=design_component,
                                    file=File(
                                        path=old_component.file.path, content=code
                                    ),
                                    update_status=(
                                        "blocked"
                                        if old_component.update_status == "blocked"
                                        else "up_to_date"
                                    ),
                                    is_deployed=old_component.is_deployed,
                                )
                            )
                        else:
                            parts = key.split(".")
                            namespace = ".".join(parts[:-1])
                            name = parts[-1]
                            conversation.add_user(
                                "Consider the following code ::"
                                f"\n\n{code}\n\n"
                                f"Add a component spec for namespace :: "
                                f"{namespace} and name :: {name}\n"
                                "Include every important detail. "
                                "Ignore logs and comments. "
                                "Very important: Extract all the hardcoded values"
                                'and add them to "purpose".'
                            )
                            response = llm.stream_text(conversation)
                            conversation.add_assistant(response)
                            jsons = extract_json(response)
                            assert len(jsons) == 1

                            design_component = Component.model_validate(jsons[0])
                            file_path = design_component.key.replace(".", "/") + ".py"
                            synced_architecture.append(
                                ImplementedComponent(
                                    design=design_component,
                                    file=File(path=file_path, content=code),
                                    update_status="blocked",
                                )
                            )
                            print_system(f"Added :: {key}")
                    except ValidationError as e:
                        if attempts == 3:
                            raise e
                        conversation.add_system(f"{type(e).__name__}({e})")
                        continue

                    break

    breakpoint()
    config["architecture"] = synced_architecture
    update_architecture_dependencies(synced_architecture)
    save_config(config)


if __name__ == "__main__":
    sys.path.append(os.path.expanduser("~/Code/modular/web/modassembly_web"))

    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    sync_configs(args.app, "lgaleana")
