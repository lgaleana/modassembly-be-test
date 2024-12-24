import json
import os
import argparse

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from ai.function_calling import Function
from utils.io import user_input
from utils.state import Conversation
from workflows.helpers import Component, build_graph, extract_json, visualize_graph


def run(app_name: str, user_story: str) -> None:
    conversation = Conversation()
    conversation.add_system(
        """You are helpful AI assistant that designs python backend architectures.

The system that you design will be exposed via a set of FastAPI endpoints. Externally, you can only rely on 3 types of infrastrucutre: databases, file system, and http requests. In the case of databases, you must use on psycopg2-binary==2.9.10 and sqlmodel==0.0.22. You must specify the models that you will use."""
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

Specify the FastAPI endpoints. Add them if missing.
Specify the external infrastructure that the system relies on. Valid values are: database, file_system, and http.
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
        "is_api": true or false whether this is a FastAPI endpoint
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

    os.makedirs(f"db/repos/{app_name}", exist_ok=True)
    with open(f"db/repos/{app_name}/config.json", "w") as f:
        json.dump(architecture_raw, f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()
    user_story = user_input("user story: ")

    run(args.app, user_story)
