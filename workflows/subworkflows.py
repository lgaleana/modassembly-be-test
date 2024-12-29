import sys
from typing import Dict, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

load_dotenv()

from ai import llm
from workflows.helpers import (
    Function,
    ImplementedComponent,
    ModelImplementationError,
    MypyError,
    REPOS,
    SQLAlchemyModel,
    create_folders_if_not_exist,
    create_tables,
    extract_from_pattern,
    run_mypy,
)
from utils.files import File
from utils.io import print_system
from utils.state import Conversation
from utils.static_analysis import RouterNotFoundError, extract_router_name


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


class ImplementationContext(BaseModel):
    component: ImplementedComponent
    user_message: Optional[str] = None
    assistant_message: Optional[str] = None
    error: Optional[Exception] = None
    tries: int = 0
    model_config = ConfigDict(arbitrary_types_allowed=True)


class MultipleCodeBlocksError(Exception):
    pass


class CompilationError(Exception):
    pass


def write_component(
    app_name: str,
    context: ImplementationContext,
    conversation: Conversation,
) -> ImplementationContext:
    sys.path.append(f"{REPOS}/{app_name}")

    component = context.component
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
    conversation.add_user(user_message)

    assistant_message = llm.stream_text(conversation)
    patterns = extract_from_pattern(assistant_message, pattern=r"```python\n(.*?)```")
    try:
        if len(patterns) > 1:
            raise MultipleCodeBlocksError(
                f"Found {len(patterns)} code blocks.\n"
                f"Write only the code for :: {component.base.model_dump()}"
            )
        code = patterns[0]

        create_folders_if_not_exist(app_name, f"app.{component.base.root.namespace}")
        folders = component.base.root.namespace.replace(".", "/")
        file_path = f"app/{folders}/{component.base.root.name}.py"
        with open(f"{REPOS}/{app_name}/{file_path}", "w") as f:
            f.write(code)

        try:
            compile(code, "<string>", "exec")
        except Exception as e:
            raise CompilationError(f"Compilation error: {e}")
        run_mypy(f"{REPOS}/{app_name}/{file_path}")
        if (
            isinstance(component.base.root, Function)
            and component.base.root.is_endpoint
        ):
            extract_router_name(code)
        elif isinstance(component.base.root, SQLAlchemyModel):
            create_tables(app_name, component.base.root.namespace, code)

        component.file = File(path=file_path, content=code)
        return ImplementationContext(
            component=component,
            user_message=user_message,
            assistant_message=assistant_message,
        )
    except (
        MultipleCodeBlocksError,
        CompilationError,
        MypyError,
        RouterNotFoundError,
        ModelImplementationError,
    ) as e:
        print_system(f"!!! Error: {e} for :: {component.base.root.name}")
        return ImplementationContext(
            component=component,
            user_message=user_message,
            assistant_message=assistant_message,
            error=e,
            tries=context.tries + 1,
        )
