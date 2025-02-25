import argparse
import json
import os
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
    MypyError,
    REPOS,
    extract_from_pattern,
    run_mypy,
    update_architecture_dependencies,
)
from workflows.subworkflows import install_requirements


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
    file_path_to_file = {f.path: f for c in architecture for f in c.files}

    components_to_remove = [c for c in architecture if c.update_status == "to_remove"]
    for component in components_to_remove:
        for file in component.files:
            file_path = f"{REPOS}/{repo_name}/{file.path}"
            if os.path.exists(file_path):
                os.remove(file_path)
        architecture.remove(component)
        print_system(f"Removed component: {component.design.key}")

    datamodels = [
        d
        for d in architecture
        if isinstance(d.design.root, DataModel) and d.update_status == "to_update"
    ]
    datamodels.sort(key=lambda x: len(x.design.root.dependencies))
    logic = [
        l
        for l in architecture
        if isinstance(l.design.root, Function)
        and l.update_status == "to_update"
        and l.design.key != "app.main"
        and l.design.key != "app.core.database.sql_adaptor"
    ]
    logic.sort(key=lambda x: len(x.design.root.dependencies))
    main = next(c for c in architecture if c.design.key == "app.main")
    sql_adaptor = next(
        (
            c
            for c in architecture
            if c.design.key == "app.core.database.sql_adaptor"
            and c.update_status == "to_update"
        ),
        None,
    )
    components_to_update = datamodels + logic
    if sql_adaptor:
        components_to_update.insert(0, sql_adaptor)
    if components_to_update or main.update_status == "to_update":
        components_to_update.append(main)

    try:
        install_requirements(repo_name, architecture)

        for component in components_to_update:
            print_system(f"Updating :: {component.design.key}")
            instructions = f"""The following technical design document describes the functionality of an entire system. Each module has a technical specification and a set of files that represent its code.

{json.dumps([c.model_dump() for c in architecture], indent=4)}

The specification has changed for the module :: {component.design.key}. Write the code for ::
        
{component.design.model_dump()}.

"""
            if isinstance(component.design.root, Function):
                instructions += """The module can map to multiple files. It's up to you to decide that. Use the best practices.
Skip `if __name__ == "__main__:"`.
Use a modular design pattern. Use classes for data models. Prefer functions for everything else. Functions shouldn't have more than 50 lines of code.
Use typing in function signatures. Use regular python code everywhere else.
Avoid catching exceptions unless specified. Let errors raise.
Use environment variables where appropriate.\n"""
            elif isinstance(component.design.root, DataModel):
                instructions += "If needed, update the `relationship` field. Use the best practices.\n"
            instructions += f"""Avoid writing __init__.py files.
Follow the repository's design patterns. Use FastAPI design patterns.
Leave no placeholders. The code must work. Write entire files.

Use the following format, so that I can extract the code:
```python
# File path: path/to/file.py
...
```"""
            conversation = Conversation()
            conversation.add_user(instructions)

            attempts = 0
            while True:
                attempts += 1
                assistant_message = llm.stream_text(conversation)
                conversation.add_assistant(assistant_message)
                code_chunks = extract_from_pattern(
                    assistant_message, pattern=r"```python\n(.*?)```"
                )

                try:
                    for code in code_chunks:
                        lines = code.split("\n")
                        first_line = lines[0]
                        code = "\n".join(lines[1:])

                        if not first_line.startswith("# File path: "):
                            raise WrongFormatError(f'Missing "# File path: " in {code}')

                        file_path = first_line.split("# File path: ")[1].strip()
                        folder_path = "/".join(file_path.split("/")[:-1])
                        create_folders_if_not_exist(repo_name, folder_path)
                        file_path = file_path.replace(f"{REPOS}/{repo_name}/", "")
                        with open(f"{REPOS}/{repo_name}/{file_path}", "w") as f:
                            f.write(code)
                        if file_path in file_path_to_file:
                            file_path_to_file[file_path].content = code
                        else:
                            file = File(path=file_path, content=code)
                            component.files.append(file)
                            file_path_to_file[file_path] = file

                    run_mypy(repo_name, [f.path for f in component.files])
                    break
                except (MypyError, WrongFormatError) as e:
                    print_system(f"!!! Error {type(e).__name__}({e})")
                    if attempts == 3:
                        print_system(f"\n\n!!! WARNING !!! Skipping mypy check!")
                        break
                    conversation.add_user(
                        f"Found the following errors ::\n\n"
                        f"{type(e).__name__}({e})\n\nPlease fix the code."
                    )

        conversation = Conversation()
        conversation.add_user(
            f"""Consider all the modules marked as "to_update", in the following technical design document:

{json.dumps([c.model_dump() for c in architecture], indent=4)}

The following modules were updated :: {[c.design.key for c in components_to_update]}

Give me a one line commit message for the changes. Go.

..."""
        )
        commit_message = llm.stream_text(conversation)

        for component in architecture:
            component.update_status = "up_to_date"
        update_architecture_dependencies(architecture)
        save_config(config)

        print_system("Pushing changes to GitHub...")
        execute_git_commands(
            [
                ["git", "add", "."],
                ["git", "commit", "-m", commit_message],
                ["git", "push", "origin", "main"],
            ],
            repo=repo_name,
        )
    except Exception as e:
        revert_changes(repo_name)
        raise e

    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    run(args.app, "")
