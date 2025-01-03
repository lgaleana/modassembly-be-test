import json
import argparse
from concurrent.futures import ThreadPoolExecutor
from typing import List

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.architecture import (
    Function,
    ImplementedComponent,
    SQLAlchemyModel,
    load_config,
    save_config,
    update_architecture_diff,
)
from utils.github import execute_git_commands, revert_changes
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import (
    MypyError,
    execute_deploy,
    group_nodes_by_dependencies,
    install_requirements,
    update_main,
)
from workflows.subworkflows import (
    ImplementationContext,
    save_templates,
    write_component,
)


def run(app_name: str, new_architecture: List[ImplementedComponent]) -> str:
    config = load_config(app_name)
    saved_architecture = config["architecture"]

    whole_architecture = saved_architecture.copy()
    update_architecture_diff(whole_architecture, new_architecture)

    conversation = Conversation()
    raw_architecture = [c.model_dump() for c in whole_architecture]
    conversation.add_user(
        f"Consider the following python architecture: {json.dumps(raw_architecture, indent=2)}"
    )

    save_templates(app_name, saved_architecture, conversation)
    install_requirements(app_name, whole_architecture)

    architecture_to_update = {}
    for component in saved_architecture:
        if not component.file:
            print_system(f"Will update :: {component.base.key}")
            architecture_to_update[component.base.key] = component
    for new_component in new_architecture:
        for old_component in saved_architecture:
            if (
                new_component.base.key == old_component.base.key
                and new_component.base.root != old_component.base.root
            ):
                print_system(f"Will update :: {new_component.base.key}")
                architecture_to_update[new_component.base.key] = new_component
                break
    print_system()

    models_to_parallelize = group_nodes_by_dependencies(
        [
            m
            for m in architecture_to_update.values()
            if isinstance(m.base.root, SQLAlchemyModel)
        ]
    )
    functions_to_parallelize = group_nodes_by_dependencies(
        [
            f
            for f in architecture_to_update.values()
            if isinstance(f.base.root, Function)
        ]
    )
    for level in models_to_parallelize + functions_to_parallelize:
        print_system(f"Implementing :: {level}\n")
        with ThreadPoolExecutor(max_workers=10) as executor:
            outputs = list(
                executor.map(
                    write_component,
                    [app_name] * len(level),
                    [
                        ImplementationContext(component=architecture_to_update[l])
                        for l in level
                    ],
                    [config["external_infrastructure"]] * len(level),
                    [conversation.copy() for _ in level],
                )
            )

        def _update(context: ImplementationContext) -> None:
            assert (
                context.user_message
                and context.assistant_message
                and context.component.file
            )
            conversation.add_user(context.user_message)
            conversation.add_assistant(context.assistant_message)
            conversation.add_user(f"I saved the code in {context.component.file.path}.")
            architecture_to_update[context.component.base.key].file = (
                context.component.file
            )

        correct_implementations = [o for o in outputs if not o.error]
        wrong_implementations = [o for o in outputs if o.error]
        for output in correct_implementations:
            _update(output)

        if not wrong_implementations:
            continue

        for output in wrong_implementations:
            error_conversation = conversation.copy()
            while True:
                assert output.user_message and output.assistant_message
                error_conversation.add_user(output.user_message)
                error_conversation.add_assistant(output.assistant_message)
                error_conversation.add_user(
                    f"Found the following errors ::\n\n{output.error}"
                )
                output = write_component(
                    app_name,
                    output,
                    config["external_infrastructure"],
                    error_conversation.copy(),
                )
                if not output.error:
                    _update(output)
                    break
                if output.tries == 3:
                    if not isinstance(output.error, MypyError):
                        assert output.error
                        revert_changes(app_name)
                        raise output.error
                    print_system(
                        f"!!!!! WARNING: Letting mypy pass ::\n\n{output.error}"
                    )
                    _update(output)
                    break

    update_architecture_diff(saved_architecture, list(architecture_to_update.values()))
    update_main(app_name, saved_architecture, config["external_infrastructure"])

    conversation.add_user("Give me a one line commit message for the changes. Go: ...")
    commit_message = llm.stream_text(conversation)
    print_system("Pushing changes to GitHub...")
    execute_git_commands(
        [
            ["git", "add", "."],
            ["git", "commit", "-m", commit_message],
            ["git", "push", "origin", "main"],
        ],
        app=app_name,
    )
    print_system("Deploying application...")
    service_url = execute_deploy(app_name)

    config["url"] = f"{service_url}/docs"
    save_config(config)
    print_system(f"{service_url}/docs")
    return f"{service_url}/docs"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    run(args.app, [])
