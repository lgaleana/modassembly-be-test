import json
import os

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.io import user_input
from utils.state import Conversation
from workflows.helpers import Component, build_graph, extract_json, visualize_graph


def run(app_name: str, user_story: str) -> None:
    conversation = Conversation()
    conversation.add_system(
        """You are a helpful AI assistant that designs backend architectures.

"""
    )
    conversation.add_user(
        f"""Consider the following user story: {user_story}.

Design the architecture (no code) of the python module (purely backend) that implements it. Be opinionated in your decisions.
Use a modular and composable design pattern. Prefer functions over classes.
Consider the control flow. For each component, specify the other components that it calls internally."""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    conversation.add_user(
        """Map the architecture into the following json.

The system will be hosted as a FastAPI service. Specify which are meant to be the API endpoints. Add them if missing.
Specify if the system relies on external infrastructure. Valid values are: database, file_system, and http.
Specify whether a component will need to install any pypi packages.
There can only be two types of components: functions and structs (like POJOs).
                          
```json
[
    {
        "name": ...,
        "purpose": ...,
        "type": "struct" or "function",
        "uses": ["The other struct or functions that this component uses internally."],
        "external_infrastructure": [
            "database", "file_system" or "http"
        ],
        "pypi_packages": ["The pypi packages that it will need"],
        "is_api": true or false whether this is an endpoint to the application
    },
    ...
]
```                       
"""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    architecture_raw = extract_json(assistant_message, pattern=r"```json\n(.*)\n```")
    architecture = {a["name"]: Component.model_validate(a) for a in architecture_raw}

    G = build_graph(list(architecture.values()))
    visualize_graph(G)

    from ai.llm_class import llmc
    llmc.conversation = conversation
    llmc.chat()

    os.makedirs(f"db/repos/{app_name}", exist_ok=True)
    with open(f"db/repos/{app_name}/config.json", "w") as f:
        json.dump(architecture_raw, f)


if __name__ == "__main__":
    app_name = user_input("app name: ")
    user_story = user_input("user story: ")
    run(app_name, user_story)
