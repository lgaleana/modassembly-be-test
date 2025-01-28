from typing import Iterator, List

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from app.logging.log_user_activity import log_user_activity
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
        design = component.design.root
        components.append(f"{design.type}: {design.key}")
        if isinstance(design, (Function, DataModel)):
            components.append(" Uses: " + ", ".join(design.dependencies))
    return "\n".join(components)


INFRASTRUCTURE = "\n".join(
    [i["name"] + ": " + i["description"] for i in AVAILABLE_INFRASTRUCTURE]
)

PROMPT = f"""You are helpful AI assistant that designs distributed backend systems.

The entire system will be hosted on Google Cloud Platform. You can spin up GCP infrastructure but you are limited to the following ones:

{INFRASTRUCTURE}

Deploying infrastructure is expensive. Select the minimum necessary.

The main logic will be executed on Google Cloud Run as a FastAPI. Cloud Run is a servelerss container desgined for web applications. Keep the business logic within the limitations of a web service. Other than APIs, it's impossible to support anything not supported by GCP.

Focus on the backend design. Let the user know if you fall into any of these limitations.

Work with the user to design a backend system. Discuss product features instead of infrastructure. Avoid showing code. Be opinionated and specific.

It's very useful to focus on the E2E flow of an http request. Start small."""


def run(
    app_name: str,
    user_message: str,
    user: str,
) -> Iterator[str]:
    config = load_config(app_name, user)
    conversation = Conversation.load(app_name, user, name="conversation_brainstorm")

    if len(conversation) == 0:
        conversation = Conversation()
        conversation.add_system(PROMPT)
        conversation.add_system(
            f"Current architecture:\n\n{present_to_llm(config['architecture'])}",
            type_="architecture",
        )

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

    if user != "lgaleana":
        log_user_activity(
            user,
            "brainstorm",
            {"conversation": conversation},
        )
