import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from app.logging.log_user_activity import log_user_activity
from utils.config.architecture import (
    DataModel,
    Function,
    Infrastructure,
    load_config,
    save_config,
)
from utils.github import execute_git_commands, revert_changes
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import (
    extract_json,
    group_nodes_by_dependencies,
    update_architecture_dependencies,
    update_main,
)
from workflows.subworkflows import first_write, install_requirements, save_templates


def run(app_name: str, user: str) -> Dict[str, Any]:
    repo_name = f"{user}_{app_name}"
    config = load_config(app_name, user)
    architecture = config["architecture"]

    conversation = Conversation.load(app_name, user, name="conversation_architecture")
    conversation.remove_last_message_type("architecture")
    conversation.add_user(
        "Consider all the changes since we last implemented the architecture. "
        "Let's update the code. "
        "Current specs vs code:\n\n"
        f"{json.dumps([c.model_dump() for c in architecture], indent=4)}"
    )

    try:
        updated_templates = save_templates(repo_name, architecture, conversation)
        install_requirements(repo_name, architecture, conversation)

        for component in architecture:
            if isinstance(component.design.root, Infrastructure):
                component.update_status = "up_to_date"
            elif component.update_status == "to_remove":
                if component.file and os.path.exists(component.file.path):
                    os.remove(component.file.path)
                architecture.remove(component)
                conversation.add_user(f"I removed {component.design.key}.")

        updated_components = {}
        while True:
            architecture_to_update = {}
            for component in architecture:
                if not component.file or component.update_status == "to_update":
                    architecture_to_update[component.design.key] = component

            models_to_parallelize = group_nodes_by_dependencies(
                [
                    m
                    for m in architecture_to_update.values()
                    if isinstance(m.design.root, DataModel)
                ]
            )
            functions_to_parallelize = group_nodes_by_dependencies(
                [
                    f
                    for f in architecture_to_update.values()
                    if isinstance(f.design.root, Function)
                ]
            )

            for level in models_to_parallelize + functions_to_parallelize:
                print_system(f"Implementing ::\n" + "\n".join(level) + "\n")
                with ThreadPoolExecutor(max_workers=10) as executor:
                    outputs = list(
                        executor.map(
                            first_write,
                            [repo_name] * len(level),
                            [architecture_to_update[l] for l in level],
                            [conversation.copy() for _ in level],
                        )
                    )
                for output in outputs:
                    assert output.component.file
                    conversation.add_user(output.user_message)
                    conversation.add_assistant(output.assistant_message)
                    conversation.add_user(
                        f"I saved the code in {output.component.file.path}."
                    )
                    architecture_to_update[output.component.design.key].file = (
                        output.component.file
                    )
                    architecture_to_update[
                        output.component.design.key
                    ].update_status = "up_to_date"
                    updated_components[output.component.design.key] = output.component

            """conversation.add_user(
                Based on the lastest changes, are there any "up_to_date" components that also need to be updated? Pay attention to the "up_to_date" components' code. Based on the code that you just wrote, which ones need to be updated? Use the following format:

```json
[namespace.name, namespace.name, ...] or [] if nothing left to update
```
            )
            response = llm.stream_text(conversation)
            conversation.add_assistant(response)
            more_updates = set(extract_json(response)[0])
            more_updates -= set(updated_templates.keys())
            if not more_updates:
                break
            for component in architecture:
                if (
                    component.design.key in more_updates
                    and component.design.key not in updated_components
                    and component.design.key not in updated_templates
                ):
                    component.update_status = "to_update" """
            break

        update_main(repo_name, architecture)
        update_architecture_dependencies(architecture)

        git_convo = conversation.copy()
        git_convo.add_user("Give me a one line commit message for the changes. Go: ...")
        commit_message = llm.stream_text(git_convo)
        print_system("Pushing changes to GitHub...")
        execute_git_commands(
            [
                ["git", "add", "."],
                ["git", "commit", "-m", commit_message],
                ["git", "push", "origin", "main"],
            ],
            repo=repo_name,
        )

        conversation = Conversation.load(
            app_name, user, name="conversation_architecture"
        )
        conversation.add_system("Implementing architecture... Done.")
        conversation.persist(app_name, user, name="conversation_architecture")
        save_config(config)

        if user != "lgaleana":
            for component in updated_components.values():
                log_user_activity(
                    user,
                    "implement",
                    {"component": component.model_dump()},
                )

        return config
    except Exception as e:
        revert_changes(repo_name)
        raise e


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    run(args.app, "")
