import os
import sys
from typing import Dict, List

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from ai import llm
from workflows.helpers import (
    Function,
    ImplementedComponent,
    REPOS,
    SQLAlchemyModel,
    create_tables,
    extract_from_pattern,
    run_mypy,
)
from utils.files import File
from utils.io import print_system
from utils.state import Conversation
from utils.static_analysis import extract_router_name


def create_folders_if_not_exist(app_name: str, namespace: str) -> None:
    packages = namespace.split(".")
    current_path = f"{REPOS}/{app_name}"
    for package in packages:
        current_path = os.path.join(current_path, package)
        if not os.path.exists(current_path):
            os.makedirs(current_path)
        init_file = os.path.join(current_path, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w") as f:
                f.write("")


def save_files(
    app_name: str,
    architecture: Dict[str, ImplementedComponent],
    external_infrastructure: List[str],
    conversation: Conversation,
) -> None:
    create_folders_if_not_exist(app_name, "app")
    create_folders_if_not_exist(app_name, "app.helpers")

    pypi = set()
    for component in architecture.values():
        for package in component.base.root.pypi_packages:
            pypi.add(package)
    with open(f"{REPOS}/{app_name}/requirements.txt", "w") as f:
        requirements_content = "\n".join(pypi)
        f.write(requirements_content)
    for file in ["deploy.sh", "Dockerfile"]:
        with open(f"{REPOS}/_template/{file}", "r") as f1, open(
            f"{REPOS}/{app_name}/{file}", "w"
        ) as f2:
            f2.write(f1.read())

    main_path = "app/main.py"
    with open(f"{REPOS}/_template/app/main.py", "r") as f, open(
        f"{REPOS}/{app_name}/{main_path}", "w"
    ) as f2:
        content = f.read()
        f2.write(content)
        conversation.add_user(f"I wrote the code for:\n\n```python\n{content}\n```")
        conversation.add_user(f"I saved the code in {main_path}.")

    if "database" in external_infrastructure:
        db_helper_path = "app/helpers/db.py"
        with open(f"{REPOS}/_template/app/helpers/db.py", "r") as f, open(
            f"{REPOS}/{app_name}/{db_helper_path}", "w"
        ) as f2:
            content = f.read()
            f2.write(content)
            conversation.add_user(f"I wrote the code for:\n\n```python\n{content}\n```")
            conversation.add_user(f"I saved the code in {db_helper_path}.")


class LevelContext(BaseModel):
    component: ImplementedComponent
    user_message: str
    assistant_message: str


def write_function(
    app_name: str,
    component: ImplementedComponent,
    conversation: Conversation,
    *,
    tries: int = 3,
) -> LevelContext:
    sys.path.append(f"{REPOS}/{app_name}")

    user_message = f"""Write the code for: {component.base.model_dump()}.

Speficications:
- The code should work (no placeholders).
- Pick the most simple implementation.
- Don't catch exceptions unless specified. Let errors raise.\n"""
    if isinstance(component.base.root, Function) and component.base.root.is_endpoint:
        user_message += (
            "- Since this function is meant to be an endpoint, "
            "a) add enough documentation and b) add proper typing, "
            "so that it's easy to use in Swagger.\n"
            "- Define pydantic models for inputs and OUTPUTS where needed.\n"
            "- Avoid condecimal.\n"
            "- Make sure that datetime in pydantic matches datetime in sqlalchemy.\n"
        )
    elif isinstance(component.base.root, SQLAlchemyModel):
        user_message += (
            "- Import Base from app.helpers.db.\n"
            "- Only use `ForeignKey` if the other model exists in the architecture.\n"
        )
    user_message += "\n```python\n...\n```"

    def _write_function(try_: int) -> LevelContext:
        conversation.add_user(user_message)
        assistant_message = llm.stream_text(conversation)
        conversation.add_assistant(assistant_message)

        try:
            patterns = extract_from_pattern(
                assistant_message, pattern=r"```python\n(.*?)```"
            )
            if len(patterns) > 1:
                raise ValueError(
                    f"Found {len(patterns)} code blocks.\n"
                    f"Write only the code for :: {component.base.model_dump()}"
                )
            code = patterns[0]

            create_folders_if_not_exist(
                app_name, f"app.{component.base.root.namespace}"
            )
            folders = component.base.root.namespace.replace(".", "/")
            file_path = f"app/{folders}/{component.base.root.name}.py"
            with open(f"{REPOS}/{app_name}/{file_path}", "w") as f:
                f.write(code)

            compile(code, "<string>", "exec")
            # check_imports(code, app_name)
            run_mypy(f"{REPOS}/{app_name}/{file_path}")
            if (
                isinstance(component.base.root, Function)
                and component.base.root.is_endpoint
            ):
                extract_router_name(code)
            elif isinstance(component.base.root, SQLAlchemyModel):
                create_tables(app_name, component.base.root.namespace, code)
        except Exception as e:
            print_system(f"!!! Error: {e} for :: {component.base.root.name}")
            if try_ == tries:
                raise e
            conversation.add_user(f"Found errors ::\n\n{e}\n\nPlease fix them.")
            return _write_function(try_ + 1)

        component.file = File(path=file_path, content=code)
        return LevelContext(
            component=component,
            user_message=user_message,
            assistant_message=assistant_message,
        )

    return _write_function(0)
