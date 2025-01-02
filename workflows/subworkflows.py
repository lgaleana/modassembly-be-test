import sys
from typing import List, Optional, Set

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


def save_templates(
    app_name: str,
    architecture: List[ImplementedComponent],
    conversation: Conversation,
) -> None:
    for file in ["deploy.sh", "Dockerfile"]:
        with open(f"{REPOS}/_template/{file}", "r") as f1, open(
            f"{REPOS}/{app_name}/{file}", "w"
        ) as f2:
            f2.write(f1.read())

    modassembly_components = {
        "main": "app/main.py",
        "modassembly.database.get_session": "app/modassembly/database/get_session.py",
        "models.User": "app/models/User.py",
        "modassembly.authentication.core.create_access_token": "app/modassembly/authentication/core/create_access_token.py",
        "modassembly.authentication.core.authenticate": "app/modassembly/authentication/core/authenticate.py",
        "modassembly.authentication.endpoints.login_api": "app/modassembly/authentication/endpoints/login_api.py",
    }
    for component in architecture:
        if not component.base.key in modassembly_components:
            continue
        module = component.base.key
        file_path = modassembly_components[module]
        package = ".".join(module.split(".")[:-1])
        create_folders_if_not_exist(app_name, f"app.{package}")
        with open(f"{REPOS}/_template/{file_path}", "r") as f1, open(
            f"{REPOS}/{app_name}/{file_path}", "w"
        ) as f2:
            content = f1.read()
            f2.write(content)
            print_system(f"Saving :: {module}")
            conversation.add_user(f"I wrote the code for:\n\n```python\n{content}\n```")
            conversation.add_user(f"I saved the code in {file_path}.")
            component.file = File(path=file_path, content=content)


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
    external_infrastructure: List[str],
    conversation: Conversation,
) -> ImplementationContext:
    sys.path.append(f"{REPOS}/{app_name}")

    component = context.component
    user_message = f"""Write the code for: {component.base.model_dump()}.

Speficications:
- The code should work (no placeholders).
- Use appropriate typing in function arguments and return types.
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
        if "authentication" in external_infrastructure:
            user_message += "- Authenticate it with app.modassembly.authentication.core.authenticate.\n"
    elif isinstance(component.base.root, SQLAlchemyModel):
        user_message += (
            "- Import Base from app.modassembly.database.get_session.\n"
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
    finally:
        sys.path.remove(f"{REPOS}/{app_name}")
