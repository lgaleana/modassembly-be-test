import argparse
import json
import os
from typing import Any, Dict, List
from dotenv import load_dotenv

load_dotenv()

from ai import llm
from ai.function_calling import Function
from utils.io import print_system, user_input
from utils.state import Conversation
from workflows.helpers import Component, BaseComponent, REPOS


initial_config = {
    "architecture": [
        BaseComponent(
            type="function",
            name="main",
            namespace="",
            purpose="The main FastAPI script",
            uses=["Other functions or structs"],
            pypi_packages=[
                "fastapi==0.115.6",
                "pydantic==2.10.3",
                "python-dotenv==1.0.1",
                "uvicorn==0.34.0",
            ],
            is_endpoint=False,
        ),
        BaseComponent(
            type="function",
            name="get_db",
            namespace="helpers",
            purpose="Initializes the database and gets a session.",
            uses=[],
            pypi_packages=["psycopg2-binary==2.9.10", "sqlalchemy==2.0.36"],
            is_endpoint=False,
        ),
    ],
    "external_infrastructure": ["database", "http"],
}


def update_config(
    config: Dict[str, Any], *, architecture: List[BaseComponent]
) -> Dict[str, Any]:
    raw_architecture = [c.model_dump() for c in architecture]
    config = {
        "name": config["name"],
        "architecture": raw_architecture,
        "external_infrastructure": config["external_infrastructure"],
    }
    with open(f"{REPOS}/{args.app}/config.json", "w") as f:
        json.dump(config, f)
    print_system(json.dumps(config, indent=2))
    return config


class AddComponent(Function[BaseComponent]):
    description = "Adds a component to the architecture."


def run(config: Dict[str, Any], user_story: str) -> None:
    architecture = [BaseComponent.model_validate(c) for c in config["architecture"]]

    conversation = Conversation()
    conversation.add_system(
        """You are helpful AI assistant that designs backend architectures.

You will be given the backend architecture of a python module that is hosted on Cloud Run as a FastAPI. The architecture will be represented as a json of the following format:
```json
[
    {{
        "type": "struct" or "function",
        "name": "The name of the struct or function",
        "namespace": "The namespace of the struct or function",
        "purpose": "What the struct or function does",
        "uses": ["The other struct or functions that this component uses internally."],
        "pypi_packages": ["The pypi packages that it will need"],
        "is_api": true or false whether this is a FastAPI endpoint
    }},
    ...
]
```

You will also be given the set of GCP infrastructure that you have access to.
Given an user story, build the architecture by adding components."""
    )

    raw_architecture = json.dumps([a.model_dump() for a in architecture], indent=4)
    conversation.add_user(f"Architecture:\n{raw_architecture}")
    conversation.add_user(
        "Available GCP infrastructure:\n- Cloud SQL.\n- External HTTP requests."
    )
    conversation.add_user(f"User story: {user_story}")
    while True:
        next = llm.stream_next(conversation, tools=[AddComponent.tool()])

        if isinstance(next, llm.RawFunctionParams):
            conversation.add_raw_tool(next)
            components = AddComponent.parse_arguments(next)
            for component in components:
                architecture.append(component)
            raw_architecture = json.dumps(
                [a.model_dump() for a in architecture], indent=4
            )
            conversation.add_tool_response(raw_architecture)
            config = update_config(config, architecture=architecture)
        else:
            conversation.add_assistant(next)
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    if not os.path.exists(f"{REPOS}/{args.app}"):
        os.makedirs(f"{REPOS}/{args.app}")
        initial_config["name"] = args.app
        update_config(initial_config, architecture=initial_config["architecture"])
    with open(f"{REPOS}/{args.app}/config.json", "r") as f:
        config = json.load(f)
    print_system(json.dumps(config, indent=2))

    user_story = user_input("user story: ")

    run(config, user_story)
