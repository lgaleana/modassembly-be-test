from typing import Iterator, List

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.config.architecture import (
    DataModel,
    Function,
    ImplementedComponent,
    load_config,
)
from utils.config.initial import AVAILABLE_INFRASTRUCTURE
from utils.state import Conversation


def present_to_llm(architecture: List[ImplementedComponent]) -> str:
    components = []
    for component in architecture:
        if component.update_status == "to_remove":
            continue
        components.append(f"{component.design.root.type}: {component.design.key}")
        if isinstance(component.design.root, (Function, DataModel)):
            if isinstance(component.design.root, Function):
                components.append(f"   {component.design.root.purpose}")
            else:
                components.append(
                    "   " + ", ".join(f.name for f in component.design.root.fields)
                )
            components.append(
                " Calls: " + ", ".join(component.design.root.dependencies)
            )
    return "\n".join(components)

PROMPT = f"""You are helpful AI assistant that designs distributed systems.

You will be working with a technical design document that contains infrastructure, datamodel and logic modules.

infrastructure represents Google Cloud Platform infrastructure that the system has access to. You can propose anything within GCP.

datamodels represent sqlalchemy models.

logic represents the business logic. datamodels and logic will be executed on Google Cloud Run as a Python FastAPI.

Your goal is to help the user amend the system architecture by adding, updating or removing modules."""


def run(
    app_name: str,
    user_message: str,
    user: str,
) -> Iterator[str]:
    config = load_config(app_name, user)
    conversation = Conversation.load(app_name, user, name="conversation_brainstorm")

    if len(conversation) == 0:
        conversation = Conversation()
        conversation.add_developer(PROMPT)

    conversation.remove_last_message_type("architecture")
    conversation.add_system(
        f"Current architecture:\n\n{present_to_llm(config['architecture'])}",
        type_="architecture",
    )
    conversation.add_user(user_message)
    response = ""
    for chunk in llm.iterate_text(conversation):
        response += chunk
        yield chunk
    conversation.add_assistant(response)
    conversation.persist(app_name, user, name="conversation_brainstorm")
