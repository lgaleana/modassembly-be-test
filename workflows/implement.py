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

    conversation = Conversation()
    conversation.add_user(
        f"""Consider the following architecture, that contains design specs and code:

{json.dumps([c.model_dump() for c in architecture], indent=4)}"""
    )

    try:
        install_requirements(repo_name, architecture, conversation)

        conversation.add_user(
            """Write the code for the components marked as "to_update". At the end write the code for app.main. Use FastAPI design patterns.
            
Each component can map to multiple files. It's up to you to decide that.
Don't worry about __init__.py files. They will be created for you.
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
                for code in code_chunks:
                    lines = code.split("\n")
                    first_line = lines[0]
                    code = "\n".join(lines[1:])

                    if not first_line.startswith("# File path: "):
                        raise WrongFormatError(f'Missing "# File path: " in {code}')

                    file_path = first_line.split("# File path: ")[1].strip()
                    with open(f"{REPOS}/{repo_name}/{file_path}", "w") as f:
                        f.write(code)

                run_mypy(repo_name)
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
                component.update_status = "up_to_date"

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
