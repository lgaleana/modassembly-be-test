import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.architecture import (
    DBModel,
    Function,
    ImplementedComponent,
    load_config,
    save_config,
    update_architecture_diff,
)
from utils.github import execute_git_commands, revert_changes
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import (
    get_architecture_to_update,
    group_nodes_by_dependencies,
    install_requirements,
    update_architecture_dependencies,
    update_main,
)
from workflows.subworkflows import (
    MODASSEMBLY_COMPONENTS,
    first_write,
    save_templates,
)


def run(app_name: str, new_architecture: List[ImplementedComponent]) -> Dict[str, Any]:
    config = load_config(app_name)
    saved_architecture = config["architecture"]

    unimplemented_architecture = saved_architecture.copy()
    update_architecture_diff(unimplemented_architecture, new_architecture)

    conversation = Conversation()
    raw_architecture = json.dumps([c.model_dump() for c in unimplemented_architecture])
    conversation.add_user(
        f"Consider the following python architecture: {raw_architecture}"
    )

    save_templates(app_name, saved_architecture, conversation)
    install_requirements(app_name, unimplemented_architecture)

    architecture_to_update = get_architecture_to_update(
        saved_architecture, new_architecture
    )
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
        print_system(f"Implementing :: {level}\n")
        try:
            with ThreadPoolExecutor(max_workers=10) as executor:
                outputs = list(
                    executor.map(
                        first_write,
                        [app_name] * len(level),
                        [architecture_to_update[l] for l in level],
                        [config["external_infrastructure"]] * len(level),
                        [conversation.copy() for _ in level],
                    )
                )
        except Exception as e:
            revert_changes(app_name)
            raise e
        for output in outputs:
            assert output.component.file
            conversation.add_user(output.user_message)
            conversation.add_assistant(output.assistant_message)
            conversation.add_user(f"I saved the code in {output.component.file.path}.")
            architecture_to_update[output.component.design.key].file = (
                output.component.file
            )

    update_architecture_diff(saved_architecture, list(architecture_to_update.values()))
    update_main(app_name, saved_architecture, config["external_infrastructure"])
    update_architecture_dependencies(saved_architecture)

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
        app=app_name,
    )

    conversation = Conversation.load(app_name)
    if len(conversation) > 0:
        conversation.add_system("Implementing the architecture...")
        conversation.add_system("Done.")
        conversation.persist(app_name=app_name)
    save_config(config)
    print_system(config["github"])
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    run(args.app, [])
