import os
import shutil
from typing import Dict, List

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from ai import llm
from workflows.helpers import Component, REPOS, extract_from_pattern, run_mypy
from utils.files import File
from utils.io import print_system
from utils.state import Conversation
from utils.static_analysis import (
    check_imports,
    extract_router_name,
    validate_response_model,
)


def save_files(
    app_name: str,
    architecture: Dict[str, Component],
    external_infrastructure: List[str],
    conversation: Conversation,
) -> None:
    pypi = set()
    for component in architecture.values():
        for package in component.pypi_packages:
            pypi.add(package)

    if os.path.exists(f"{REPOS}/{app_name}/app"):
        shutil.rmtree(f"{REPOS}/{app_name}/app")
    os.mkdir(f"{REPOS}/{app_name}/app")
    with open(f"{REPOS}/{app_name}/__init__.py", "w") as f:
        f.write("")
    with open(f"{REPOS}/{app_name}/app/__init__.py", "w") as f:
        f.write("")
    with open(f"{REPOS}/{app_name}/requirements.txt", "w") as f:
        requirements_content = "\n".join(pypi)
        f.write(requirements_content)
    os.makedirs(f"{REPOS}/{app_name}/app/components", exist_ok=True)
    with open(f"{REPOS}/{app_name}/app/components/__init__.py", "w") as f:
        f.write("")
    for file in ["deploy.sh", "Dockerfile"]:
        with open(f"{REPOS}/_template/{file}", "r") as f1, open(
            f"{REPOS}/{app_name}/{file}", "w"
        ) as f2:
            f2.write(f1.read())

    main_path = "app/main.py"
    os.makedirs(os.path.dirname(f"{REPOS}/{app_name}/{main_path}"), exist_ok=True)
    with open(f"{REPOS}/_template/app/main.py", "r") as f, open(
        f"{REPOS}/{app_name}/{main_path}", "w"
    ) as f2:
        content = f.read()
        f2.write(content)
        conversation.add_user(f"I wrote the code for:\n\n```python\n{content}\n```")
        conversation.add_user(f"I saved the code in {main_path}.")

    if "database" in external_infrastructure:
        db_helper_path = "app/helpers/db.py"
        os.makedirs(
            os.path.dirname(f"{REPOS}/{app_name}/{db_helper_path}"), exist_ok=True
        )
        with open(f"{REPOS}/{app_name}/app/helpers/__init__.py", "w") as f:
            f.write("")
        with open(f"{REPOS}/_template/app/helpers/db.py", "r") as f, open(
            f"{REPOS}/{app_name}/{db_helper_path}", "w"
        ) as f2:
            content = f.read()
            f2.write(content)
            conversation.add_user(f"I wrote the code for:\n\n```python\n{content}\n```")
            conversation.add_user(f"I saved the code in {db_helper_path}.")


class LevelContext(BaseModel):
    component: Component
    user_message: str
    assistant_message: str
    file: File


def write_function(
    app_name: str,
    component: Component,
    conversation: Conversation,
    *,
    tries: int = 3,
) -> LevelContext:
    user_message = f"Write the actual working code (no placeholders) for: {component.model_dump()}\n"
    if component.is_endpoint:
        user_message += (
            "Since this function is meant to be an endpoint, "
            "1) add enough documentation and 2) add very specific typing, "
            "so that it's easy to use in Swagger. "
            "Use pydantic models in the FastAPI decorator, instead of SQLAlchemy models.\n"
        )
    user_message += "\n```python\n...\n```"

    def _write_function(try_: int) -> LevelContext:
        conversation.add_user(user_message)
        assistant_message = llm.stream_text(conversation)
        conversation.add_assistant(assistant_message)

        code = extract_from_pattern(assistant_message, pattern=r"```python\n(.*?)```")
        file_path = f"app/components/{component.name}.py"
        with open(f"{REPOS}/{app_name}/{file_path}", "w") as f:
            f.write(code)

        try:
            compile(code, "<string>", "exec")
            # check_imports(code, app_name)
            run_mypy(f"{REPOS}/{app_name}/{file_path}")
            if component.is_endpoint:
                extract_router_name(code)
                validate_response_model(code)
        except Exception as e:
            print_system(f"!!! Error: {e} for :: {component.name}")
            if try_ == tries:
                raise e
            conversation.add_user(f"Found errors ::\n\n{e}\n\nPlease fix them.")
            return _write_function(try_ + 1)

        return LevelContext(
            component=component,
            user_message=user_message,
            assistant_message=assistant_message,
            file=File(path=file_path, content=code),
        )

    return _write_function(0)
