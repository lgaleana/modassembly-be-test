import json
import os
import subprocess
from typing import Dict

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from ai import llm
from workflows.helpers import Component, REPOS, extract_from_pattern
from utils.files import File
from utils.io import print_system
from utils.state import Conversation
from utils.static_analysis import check_imports


def save_files(
    app_name: str,
    architecture: Dict[str, Component],
    conversation: Conversation,
) -> None:
    pypi = set()
    has_db = False
    for component in architecture.values():
        for package in component.pypi_packages:
            pypi.add(package)
        for external in component.external_infrastructure:
            if external == "database":
                has_db = True

    os.mkdir(f"{REPOS}/{app_name}/app")
    with open(f"{REPOS}/{app_name}/__init__.py", "w") as f:
        f.write("")
    with open(f"{REPOS}/{app_name}/app/__init__.py", "w") as f:
        f.write("")

    main_path = f"{REPOS}/{app_name}/app/main.py"
    os.makedirs(os.path.dirname(main_path), exist_ok=True)
    with open(f"{REPOS}/_template/main.py", "r") as f, open(main_path, "w") as f2:
        content = f.read()
        f2.write(content)
        conversation.add_user(f"I wrote the code for:\n\n```python\n{content}\n```")
        conversation.add_user(f"I saved the code in {main_path}.")

    with open(f"{REPOS}/_template/requirements.txt", "r") as f:
        requirements_content = f.read()
    requirements_content += "\n" + "\n".join(pypi)

    if has_db:
        db_helper_path = f"{REPOS}/{app_name}/app/helpers/db.py"
        os.makedirs(os.path.dirname(db_helper_path), exist_ok=True)
        with open(f"{REPOS}/{app_name}/app/helpers/__init__.py", "w") as f:
            f.write("")
        with open(f"{REPOS}/_template/helpers/db.py", "r") as f, open(
            db_helper_path, "w"
        ) as f2:
            content = f.read()
            f2.write(content)
            conversation.add_user(f"I wrote the code for:\n\n```python\n{content}\n```")
            conversation.add_user(f"I saved the code in {db_helper_path}.")
        requirements_content += "\npsycopg2-binary==2.9.10\nsqlmodel==0.0.22"

    for file in ["deploy.sh", "Dockerfile"]:
        with open(f"{REPOS}/_template/{file}", "r") as f1, open(
            f"{REPOS}/{app_name}/{file}", "w"
        ) as f2:
            f2.write(f1.read())

    requirements_path = f"{REPOS}/{app_name}/requirements.txt"
    with open(f"{REPOS}/{app_name}/requirements.txt", "w") as f:
        f.write(requirements_content)
        conversation.add_user(
            f"I wrote the code for:\n\n```python\n{requirements_content}\n```"
        )
        conversation.add_user(f"I saved the code in {requirements_path}.")

    os.makedirs(f"{REPOS}/{app_name}/app/components", exist_ok=True)
    with open(f"{REPOS}/{app_name}/app/components/__init__.py", "w") as f:
        f.write("")

    print_system("Installing requirements...")
    subprocess.run(
        [
            "python3",
            "-m",
            "pip",
            "install",
            "-r",
            f"{REPOS}/{app_name}/requirements.txt",
        ],
        check=True,
    )


class LevelContext(BaseModel):
    component: Component
    user_message: str
    assistant_message: str
    file: File


def write_function(
    app_name: str, component: Component, conversation: Conversation, *, tries: int = 2
) -> LevelContext:
    def _write_function(try_: int) -> LevelContext:
        user_message = f"""Write the code for: {component.model_dump()}. Use the following format:
```python
...
```"""
        conversation.add_user(user_message)
        assistant_message = llm.stream_text(conversation)

        code = extract_from_pattern(assistant_message, pattern=r"```python\n(.*?)```")

        try:
            compile(code, "<string>", "exec")
            check_imports(code)
        except Exception as e:
            import json

            print_system(json.dumps(conversation, indent=2))
            print_system(e)
            breakpoint()
            conversation.add_user(assistant_message)
            if try_ == tries:
                raise e
            conversation.add_user(f"Found errors :: {e}. Please fix them.")
            return _write_function(try_ + 1)

        file_path = f"app/components/{component.name}.py"
        with open(f"{REPOS}/{app_name}/{file_path}", "w") as f:
            f.write(code)
        return LevelContext(
            component=component,
            user_message=user_message,
            assistant_message=assistant_message,
            file=File(path=file_path, content=code),
        )

    return _write_function(0)
