import argparse
import json
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.config.architecture import (
    DataModel,
    Function,
    load_config,
    save_config,
)
from utils.files import File, create_folders_if_not_exist
from utils.github import execute_git_commands, revert_changes
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import (
    MODASSEMBLY_COMPONENTS,
    MypyError,
    REPOS,
    extract_from_pattern,
    group_nodes_by_dependencies,
    run_mypy,
    update_main,
)
from workflows.subworkflows import install_requirements, save_templates


class WrongFormatError(Exception):
    pass


def run(app_name: str, user: str) -> Dict[str, Any]:
    repo_name = f"{user}_{app_name}"
    execute_git_commands(
        [
            ["git", "add", "."],
            ["git", "commit", "-m", "Commit config"],
            ["git", "push", "origin", "main"],
        ],
        repo=repo_name,
        check=False,
    )

    config = load_config(app_name, user)
    architecture = config["architecture"]

    conversation = Conversation()
    conversation.add_user(
        f"""Consider the following architecture, that contains design specs and code:

{json.dumps([c.model_dump() for c in architecture], indent=4)}

We will update the components marked as `"to_update"`"""
    )

    try:
        save_templates(repo_name, architecture, conversation)
        install_requirements(repo_name, architecture, conversation)

        architecture_to_update = {}
        for component in architecture:
            if component.update_status == "to_update":
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
            for component_key in level:
                component = architecture_to_update[component_key]

                conversation.add_user(
                    f"""Write the code for {component.design}.
                    
This component can map to multiple files. It's up to you decide that.
Use environment variables where appropriate.
Don't catch exceptions unless specified. Let errors raise.
Use typing in function signatures.

Use the following format, so that I can extract the code:

```python
# File path: path/to/file.py
...
```"""
                )

                attempts = 0
                while True:
                    attempts += 1
                    assistant_message = llm.stream_text(conversation)
                    conversation.add_assistant(assistant_message)
                    code_chunks = extract_from_pattern(
                        assistant_message, pattern=r"```python\n(.*?)```"
                    )

                    try:
                        run_mypy(repo_name)

                        for code in code_chunks:
                            lines = code.split("\n")
                            first_line = lines[0]
                            code = "\n".join(lines[1:])

                            if not first_line.startswith("# File path: "):
                                raise WrongFormatError(
                                    f'Missing "# File path: " in {code}'
                                )

                            file_path = first_line.split("# File path: ")[1].strip()

                            file = File(path=file_path, content=code)
                            component.files.append(file)
                        break
                    except (MypyError, WrongFormatError) as e:
                        print_system(f"!!! Error {type(e).__name__}({e})")
                        if attempts == 3:
                            if isinstance(e, MypyError):
                                print_system(f"!!!!! WARNING: Letting mypy pass.")
                                break
                        conversation.add_user(
                            f"Found the following errors ::\n\n"
                            f"{type(e).__name__}({e})\n\nPlease fix the code."
                        )

        for component in architecture:
            if component.update_status == "to_update":
                for file in component.files:
                    if component.design.key not in MODASSEMBLY_COMPONENTS:
                        create_folders_if_not_exist(
                            repo_name, component.design.root.namespace
                        )
                        with open(f"{REPOS}/{repo_name}/{file.path}", "w") as f:
                            f.write(file.content)
                component.update_status = "up_to_date"
        update_main(repo_name, architecture)

        arch_conversation = Conversation.load(
            app_name, user, name="conversation_architecture"
        )
        arch_conversation.add_system("Implementing architecture... Done.")
        arch_conversation.persist(app_name, user, name="conversation_architecture")
        save_config(config)

        conversation.add_user(
            "Give me a one line commit message for the changes. Go: ..."
        )
        commit_message = llm.stream_text(conversation)
        print_system("Pushing changes to GitHub...")
        execute_git_commands(
            [
                ["git", "add", "."],
                ["git", "commit", "-m", commit_message],
                ["git", "push", "origin", "main"],
            ],
            repo=repo_name,
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
