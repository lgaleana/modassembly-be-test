from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

load_dotenv()

from ai import llm
from utils.architecture import DBModel, Function, ImplementedComponent
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
    user: str,
) -> None:
    for file in [".gitignore"]:
        with open(f"{REPOS}/fastapi-template/{file}", "r") as f1, open(
            f"{REPOS}/{user}/{app_name}/{file}", "w"
        ) as f2:
            f2.write(f1.read())

    for component in architecture:
        if not component.design.key in MODASSEMBLY_COMPONENTS:
            continue
        module = component.design.key
        file_path = MODASSEMBLY_COMPONENTS[module]
        package = ".".join(module.split(".")[:-1])
        create_folders_if_not_exist(app_name, f"app.{package}", user)
        with open(f"{REPOS}/fastapi-template/{file_path}", "r") as f1, open(
            f"{REPOS}/{user}/{app_name}/{file_path}", "w"
        ) as f2:
            content = f1.read()
            f2.write(content)
            print_system(f"Saving :: {module}")
            conversation.add_user(f"I wrote the code for:\n\n```python\n{content}\n```")
            conversation.add_user(f"I saved the code in {file_path}.")
            component.file = File(path=file_path, content=content)


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
    app_name: str,
    user: str,
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
    try:
        if len(patterns) > 1:
            raise MultipleCodeBlocksError(
                f"Found {len(patterns)} code blocks.\n"
                f"Write only the code for :: {component.design.model_dump()}"
            )
        code = patterns[0]

        create_folders_if_not_exist(
            app_name, f"app.{component.design.root.namespace}", user
        )
        folders = component.design.root.namespace.replace(".", "/")
        file_path = f"app/{folders}/{component.design.root.name}.py"
        with open(f"{REPOS}/{user}/{app_name}/{file_path}", "w") as f:
            f.write(code)

        run_mypy(app_name, file_path)
        if (
            isinstance(component.design.root, Function)
            and component.design.root.is_endpoint
        ):
            extract_router_name(code)
        elif isinstance(component.design.root, DBModel):
            create_tables(app_name, code)

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
        print_system(
            f"!!! Error for :: {component.design.root.name}\n\n"
            f"{type(e).__name__}({e})"
        )
        if attempts == 3:
            if isinstance(e, MypyError):
                assert code is not None
                print_system(f"!!!!! WARNING: Letting mypy pass.")
                component.file = File(path=file_path, content=code)
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
            app_name, user, user_message, component, conversation, attempts
        )


def first_write(
    app_name: str,
    component: ImplementedComponent,
    external_infrastructure: List[str],
    conversation: Conversation,
    user: str,
) -> ImplementationContext:
    instructions = f"""Write the code for: {component.design.model_dump()}.

    Speficications:
    - The code should work (no placeholders).
    - Use absolute imports.
    - Use appropriate typing in function arguments and return types.
    - Pick the most simple implementation.
    - Don't catch exceptions unless specified. Let errors raise.\n"""
    if isinstance(component.design.root, Function):
        if component.design.root.is_endpoint:
            instructions += (
                "- Since this function is meant to be an endpoint, "
                "a) add enough documentation and b) add proper typing, "
                "so that it's easy to use in Swagger.\n"
                "- Define pydantic models for inputs and OUTPUTS where needed.\n"
                "- Use the most simple types for pydantic models.\n"
            )
            if "authentication" in external_infrastructure:
                instructions += "- Authenticate it with app.modassembly.authentication.authenticate.\n"
        instructions += (
            "- mypy will be run over the code, so implement the function in a way that it passes mypy.\n"
            "- When using SQLALchemy models, access the actual column values. "
            "Example for a string attribute: `model.attribute.__str__()`.\n"
            f" - {component.design.root.purpose}\n"
        )
    elif isinstance(component.design.root, DBModel):
        instructions += (
            "- Import Base from app.modassembly.database.sql.get_sql_session.\n"
            "- Only use `ForeignKey` if the other model exists in the architecture.\n"
        )
    instructions += "\n```python\n...\n```"
    return write_component(app_name, user, instructions, component, conversation)
