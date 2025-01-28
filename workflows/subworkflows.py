import os
import subprocess
import venv
from typing import Dict, List

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

load_dotenv()

from ai import llm
from utils.config.architecture import DataModel, Function, ImplementedComponent
from workflows.helpers import (
    MODASSEMBLY_COMPONENTS,
    ModelImplementationError,
    MypyError,
    REPOS,
    create_tables,
    extract_from_pattern,
    run_mypy,
)
from utils.files import File, create_folders_if_not_exist
from utils.io import print_system
from utils.state import Conversation
from utils.static_analysis import RouterNotFoundError, extract_router_name


def save_templates(
    app_name: str,
    architecture: List[ImplementedComponent],
    conversation: Conversation,
) -> Dict[str, ImplementedComponent]:
    for file in [".gitignore", "README.md"]:
        with open(f"{REPOS}/fastapi-template/{file}", "r") as f1, open(
            f"{REPOS}/{app_name}/{file}", "w"
        ) as f2:
            content = f1.read()
            f2.write(content)
            conversation.add_user(f"I wrote:\n\n{content}")
            conversation.add_user(f"I saved it in {file}.")

    updated_components = {}
    for component in architecture:
        if not component.design.key in MODASSEMBLY_COMPONENTS:
            continue
        file_path = MODASSEMBLY_COMPONENTS[component.design.key]
        create_folders_if_not_exist(app_name, component.design.root.namespace)
        with open(f"{REPOS}/fastapi-template/{file_path}", "r") as f1, open(
            f"{REPOS}/{app_name}/{file_path}", "w"
        ) as f2:
            content = f1.read()
            f2.write(content)
            print_system(f"Saving :: {component.design.key}")
            conversation.add_user(f"I wrote the code for:\n\n```python\n{content}\n```")
            conversation.add_user(f"I saved the code in {file_path}.")
            component.file = File(path=file_path, content=content)
            component.update_status = "up_to_date"
            updated_components[component.design.key] = component
    return updated_components


class InstallRequirementsError(Exception):
    pass


def install_requirements(
    app_name: str,
    architecture: List[ImplementedComponent],
    conversation: Conversation,
) -> None:
    pypi_packages = set()
    for component in architecture:
        if isinstance(component.design.root, DataModel) or isinstance(
            component.design.root, Function
        ):
            pypi_packages.update(component.design.root.pypi_packages)
    requirements_path = f"{REPOS}/{app_name}/requirements.txt"
    with open(requirements_path, "w") as f:
        content = "\n".join(pypi_packages)
        f.write(content)
    conversation.add_user(f"I wrote:\n\n{content}")
    conversation.add_user(f"I saved it in {requirements_path}.")

    venv_path = f"{REPOS}/{app_name}/venv"
    os.makedirs(venv_path, exist_ok=True)
    venv.create(venv_path, with_pip=True)
    venv_python = os.path.join(venv_path, "bin", "python3")
    print_system("Installing requirements...")
    output = subprocess.run(
        [venv_python, "-m", "pip", "install", "-r", requirements_path],
        check=False,
        capture_output=True,
        text=True,
    )
    print_system(output.stdout)
    print_system(output.stderr)
    if output.returncode != 0:
        raise InstallRequirementsError(f"{output.stdout}\n{output.stderr}")


class ImplementationContext(BaseModel):
    component: ImplementedComponent
    user_message: str
    assistant_message: str
    model_config = ConfigDict(arbitrary_types_allowed=True)


class MultipleCodeBlocksError(Exception):
    pass


class CompilationError(Exception):
    pass


def write_component(
    repo_name: str,
    user_message: str,
    component: ImplementedComponent,
    conversation: Conversation,
    attempts: int = 0,
) -> ImplementationContext:
    attempts += 1

    conversation.add_user(user_message)
    assistant_message = llm.stream_text(conversation)
    patterns = extract_from_pattern(assistant_message, pattern=r"```python\n(.*?)```")

    code = None
    folders = component.design.root.namespace.replace(".", "/")
    file_path = f"{folders}/{component.design.root.name}.py"
    try:
        if len(patterns) > 1:
            raise MultipleCodeBlocksError(
                f"Found {len(patterns)} code blocks.\n"
                f"Write only the code for :: {component.design.model_dump()}"
            )
        code = patterns[0]

        create_folders_if_not_exist(repo_name, component.design.root.namespace)
        with open(f"{REPOS}/{repo_name}/{file_path}", "w") as f:
            f.write(code)

        run_mypy(repo_name, file_path)
        if (
            isinstance(component.design.root, Function)
            and component.design.root.is_endpoint
        ):
            extract_router_name(code)
        elif isinstance(component.design.root, DataModel) and any(
            "sqlalchemy" in d for d in component.design.root.dependencies
        ):
            create_tables(repo_name, code)

        component.file = File(path=file_path, content=code)
        component.update_status = "up_to_date"
        return ImplementationContext(
            component=component,
            user_message=user_message,
            assistant_message=assistant_message,
        )
    except (
        MultipleCodeBlocksError,
        MypyError,
        RouterNotFoundError,
        ModelImplementationError,
    ) as e:
        print_system(
            f"!!! Error for :: {component.design.root.name}\n\n"
            f"{type(e).__name__}({e})"
        )
        if file_path and os.path.exists(f"{REPOS}/{repo_name}/{file_path}"):
            os.remove(f"{REPOS}/{repo_name}/{file_path}")

        if attempts == 3:
            if isinstance(e, MypyError) and file_path:
                assert code is not None
                print_system(f"!!!!! WARNING: Letting mypy pass.")

                component.file = File(path=file_path, content=code)
                component.update_status = "up_to_date"
                return ImplementationContext(
                    component=component,
                    user_message=user_message,
                    assistant_message=assistant_message,
                )
            raise e

        conversation.add_assistant(assistant_message)
        conversation.add_user(
            f"Found the following errors ::\n\n"
            f"{type(e).__name__}({e})\n\nPlease fix the code."
        )
        return write_component(
            repo_name, user_message, component, conversation, attempts
        )


def first_write(
    repo_name: str,
    component: ImplementedComponent,
    conversation: Conversation,
) -> ImplementationContext:
    instructions = f"""Write the code for: {component.design.model_dump_json(indent=4)}.

The code should work E2E. Leave no placeholders.
Use absolute imports.
Use typing in function arguments and return types.
Use environment variables instead of placeholders.
Don't catch exceptions unless specified. Let errors raise.\n"""
    if isinstance(component.design.root, Function):
        if component.design.root.is_endpoint:
            instructions += (
                "Since this function is meant to be an endpoint, "
                "a) add enough documentation and b) add proper typing, "
                "so that it's easy to use in Swagger.\n"
                "Define pydantic models for inputs and OUTPUTS where needed.\n"
                "Use the most simple types for pydantic models.\n"
            )
        instructions += (
            "mypy will be run over the code, so implement the function in a way that it passes mypy.\n"
            "When using SQLALchemy models, access the actual column values. "
            "Example for a string attribute: `model.attribute.__str__()`.\n"
            f" - {component.design.root.purpose}\n"
        )
    elif isinstance(component.design.root, DataModel) and any(
        "sqlalchemy" in d for d in component.design.root.dependencies
    ):
        instructions += (
            "Import Base from app.modassembly.database.sql.get_sql_session.\n"
            "Only use `ForeignKey` if the other model exists in the architecture.\n"
        )
    instructions += "\n```python\n...\n```"
    return write_component(repo_name, instructions, component, conversation)
