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
    load_config,
    save_config,
)
from utils.files import File
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import REPOS, extract_json


def sync_configs(app_name: str, user: str) -> None:
    from workflows.design import PROMPT

    config = load_config(app_name, user)
    architecture = {c.design.key: c for c in config["architecture"]}

    conversation = Conversation()
    conversation.add_system(PROMPT)
    raw_architecture = json.dumps(
        [c.design.model_dump() for c in architecture.values()]
    )
    conversation.add_user(f"Current architecture: {raw_architecture}")

    synced_architecture = []
    app_path = f"{REPOS}/{user}_{app_name}/app"
    for root, _, files in os.walk(app_path):
        for file in files:
            if file.endswith(".py") and not file.endswith("__init__.py"):
                relative_path = os.path.relpath(root, app_path)
                key = file.replace(".py", "")
                if relative_path != ".":
                    key = os.path.join(relative_path, key)
                    key = key.replace(os.sep, ".")
                    key = f"app.{key}"
                else:
                    key = file.replace(".py", "")
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
                                    "Update the component design. "
                                    "VERY IMPORTANT: Extract the exact hardcoded values."
                                )
                                response = llm.stream_text(conversation)
                                conversation.add_assistant(response)
                                jsons = extract_json(response)
                                assert len(jsons) == 1
                                design_component = Component.model_validate(jsons[0])
                                print_system(f"Updated :: {key}")
                            else:
                                design_component = old_component.design
                        else:
                            parts = key.split(".")
                            namespace = ".".join(parts[:-1])
                            name = parts[-1]
                            conversation.add_user(
                                "Consider the following code ::"
                                f"\n\n{code}\n\n"
                                f"Add a component design for namespace :: "
                                f"{namespace} and name :: {name}. "
                                "VERY IMPORTANT: Extract the exact hardcoded values."
                            )
                            response = llm.stream_text(conversation)
                            conversation.add_assistant(response)
                            jsons = extract_json(response)
                            assert len(jsons) == 1
                            design_component = Component.model_validate(jsons[0])
                            print_system(f"Added :: {key}")
                    except ValidationError as e:
                        if attempts == 3:
                            raise e
                        conversation.add_system(f"{type(e).__name__}({e})")
                        continue

                    synced_architecture.append(
                        ImplementedComponent(
                            design=design_component,
                            file=File(path=full_path, content=code),
                            is_deployed=(
                                old_component.is_deployed
                                if old_component is not None
                                else False
                            ),
                        )
                    )
                    break
    breakpoint()
    config["architecture"] = synced_architecture
    save_config(config)


if __name__ == "__main__":
    sys.path.append(os.path.expanduser("~/Code/modular/web/modassembly_web"))

    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    sync_configs(args.app, "lgaleana")
