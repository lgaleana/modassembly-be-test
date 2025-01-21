from dotenv import load_dotenv

load_dotenv()

from ai import llm
from app.logging.log_user_activity import log_user_activity
from utils.config.architecture import (
    load_config,
    present_to_llm,
)
from utils.config.initial import AVAILABLE_INFRASTRUCTURE
from utils.state import Conversation


INFRASTRUCTURE = "\n".join([i["name"] for i in AVAILABLE_INFRASTRUCTURE])

PROMPT = f"""You are helpful AI assistant that designs distributed backend systems.

The entire system will be hosted on Google Cloud Platform.

Think of the architecture in terms of components that can be composed together. There are three types of components: infrastructure, data models and functions.

Infrastructure represent the GCP infrastructure. Available infrastructure:
{INFRASTRUCTURE}

Think of data models as data sinks. They represent database tables.

At some point, data models and functions will be implemented into actual code (you don't have access to that code). They will be executed on Google Cloud Run as a FastAPI. Cloud Run is a servelerss container desgined for web applications. What this means is that you must be careful about how you design your business logic. Keep it within the limitations of a web service. For anything else, rely on the other infrastructure.

Functions represent the business logic. The main goal is to design an architecture that is malleable, easy to refactor and easy to maintain. You will accomplish this by using modularity and the single responsibility principle. Use python naming conventions. Each function should do only one thing. Functions should map to less than 100 lines of code.

Avoid showing code. Speak at a high level. It's very useful to explain the E2E user flow. For each component, specify its dependencies."""


def run(
    app_name: str,
    user_message: str,
    user: str,
) -> Conversation:
    config = load_config(app_name, user)
    conversation = Conversation.load(app_name, user)

    if len(conversation) == 0:
        conversation = Conversation()
        conversation.add_system(PROMPT, type_="brainstorm_prompt")

    conversation.remove_last_message_type("architecture")
    conversation.add_system(
        f"Current architecture:\n\n{present_to_llm(config['architecture'])}",
        type_="architecture",
    )
    conversation.add_user(user_message)
    response = llm.stream_text(conversation)
    conversation.add_assistant(response)
    conversation.persist(app_name, user)

    if user != "lgaleana":
        log_user_activity(
            user,
            "brainstorm",
            {
                "config": {
                    "name": config["name"],
                    "user": config["user"],
                    "architecture": [c.model_dump() for c in config["architecture"]],
                    "github": config["github"],
                    "url": config["url"],
                },
                "conversation": conversation,
            },
        )

    return conversation
