import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.architecture import (
    DBModel,
    Function,
    load_config,
    save_config,
)
from utils.github import execute_git_commands, revert_changes
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import (
    group_nodes_by_dependencies,
    install_requirements,
    update_architecture_dependencies,
    update_main,
)
from workflows.subworkflows import first_write, save_templates


def run(app_name: str, user: str) -> Dict[str, Any]:
    repo_name = f"{user}_{app_name}"
    config = load_config(app_name, user)
    architecture = config["architecture"]

    conversation = Conversation()
    raw_architecture = json.dumps([c.model_dump() for c in architecture])
    conversation.add_user(
        f"Consider the following python architecture: {raw_architecture}"
    )

    save_templates(repo_name, architecture, conversation)
    install_requirements(repo_name, architecture)

    architecture_to_update = {c.design.key: c for c in architecture if c.file is None}
    models_to_parallelize = group_nodes_by_dependencies(
        [
            m
            for m in architecture_to_update.values()
            if isinstance(m.design.root, DBModel)
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
                        [config["external_infrastructure"]] * len(level),
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

    update_main(repo_name, architecture, config["external_infrastructure"])
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

    conversation = Conversation.load(app_name, user)
    if len(conversation) > 0:
        conversation.add_system("Implementing the architecture...")
        conversation.add_system("Done.")
        conversation.persist(app_name, user)
    save_config(config)
    print_system(config["github"])
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    run(args.app, "")
