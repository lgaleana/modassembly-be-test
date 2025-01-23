import argparse
import json
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
    MODASSEMBLY_COMPONENTS,
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

    save_templates(repo_name, architecture, conversation)
    install_requirements(repo_name, architecture, conversation)

    architecture_to_update = {c.design.key: c for c in architecture if c.file is None}
    for dependency in list(architecture_to_update.keys()):
        for component in architecture:
            if (
                not isinstance(component.design.root, Infrastructure)
                and dependency in component.design.root.dependencies
                and dependency not in MODASSEMBLY_COMPONENTS
            ):
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
        print_system(f"Implementing :: " + "\n".join(level) + "\n")
        try:
            with ThreadPoolExecutor(max_workers=10) as executor:
                outputs = list(
                    executor.map(
                        first_write,
                        [repo_name] * len(level),
                        [architecture_to_update[l] for l in level],
                        [conversation.copy() for _ in level],
                    )
                )
        except Exception as e:
            revert_changes(repo_name)
            raise e
        for output in outputs:
            assert output.component.file
            conversation.add_user(output.user_message)
            conversation.add_assistant(output.assistant_message)
            conversation.add_user(f"I saved the code in {output.component.file.path}.")
            architecture_to_update[output.component.design.key].file = (
                output.component.file
            )

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

    save_config(config)
    conversation = Conversation.load(app_name, user)
    if len(conversation) > 0:
        conversation.add_system(
            "Implementing the architecture... Done.", type_="implementation"
        )
        conversation.persist(app_name, user)
    print_system(config["github"])

    if user != "lgaleana":
        for _ in architecture:
            log_user_activity(
                user,
                "implement-component",
                {
                    "config": {
                        "name": config["name"],
                        "user": config["user"],
                        "architecture": [
                            c.model_dump() for c in config["architecture"]
                        ],
                        "github": config["github"],
                        "url": config["url"],
                    },
                    "conversation": conversation,
                },
            )

    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    run(args.app, "")
