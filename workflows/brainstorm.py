from typing import Iterator

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


INFRASTRUCTURE = "\n".join(
    [i["name"] + ": " + i["description"] for i in AVAILABLE_INFRASTRUCTURE]
)

PROMPT = f"""You are helpful AI assistant that designs distributed backend systems.

The entire system will be hosted on Google Cloud Platform.

You can choose from the following infrastructure. Deploying infrastructure is expensive. Select the minimum necessary.
{INFRASTRUCTURE}

The main logic will be executed on Google Cloud Run as a FastAPI. Cloud Run is a servelerss container desgined for web applications. Keep the business logic within the limitations of a web service.

Work with the user to design a backend system. Discuss product features instead of infrastructure. Avoid showing code. Be opinionated and specific. Start small.

It's very useful to focus on E2E user flows. For each flow, use the following format:

...:
1. ...
2. ...
...

..."""


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
