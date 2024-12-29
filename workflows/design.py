import argparse
import json
import os
from typing import Any, Dict
from dotenv import load_dotenv

load_dotenv()

from ai import llm
from ai.function_calling import Function
from utils.architecture import (
    Component,
    Function as FunctionComponent,
    ImplementedComponent,
    load_config,
    save_config,
)
from utils.io import user_input
from utils.state import Conversation
from workflows.helpers import REPOS


initial_config = {
    "architecture": [
        FunctionComponent(
            name="main",
            namespace="",
            purpose="The main FastAPI script.",
            uses=["Other sqlalchemymodels or functions"],
            pypi_packages=[
                "fastapi==0.115.6",
                "pydantic==2.10.3",
                "python-dotenv==1.0.1",
                "uvicorn==0.34.0",
            ],
            is_endpoint=False,
        ),
        FunctionComponent(
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


class AddComponent(Function[Component]):
    description = "Adds a sqlalchemymodel or function to the architecture."


def run(config: Dict[str, Any], user_story: str) -> None:
    architecture = [c.base.root for c in config["architecture"]]

    conversation = Conversation()
    conversation.add_system(
        """You are helpful AI assistant that designs backend architectures.

You will be given the backend architecture of a python module that is hosted on Cloud Run as a FastAPI. The architecture will be represented as a json in the following format:
```json
[
    {{
        "type": "sqlalchemymodel",
        "name": "The name of the sqlalchemymodel",
        "namespace": "The namespace of the sqlalchemymodel",
        "fields": ["The fields of the sqlalchemymodel"],
        "associations": ["The other sqlalchemymodels that this model is associated with"],
        "pypi_packages": ["The pypi packages that it will need"],
    }},
     {{
        "type": "function",
        "name": "The name of the function",
        "namespace": "The namespace of the function",
        "purpose": "What the component does",
        "uses": ["The other namespace.functions or namespace.sqlalchemymodels that this component uses internally."],
        "pypi_packages": ["The pypi packages that it will need"],
        "is_endpoint": true or false whether this is a FastAPI endpoint
    }},
    ...
]
```

You will also be given the set of GCP infrastructure that you have access to.
Given an user story, build the architecture by adding components. Prefer the most simple design."""
    )

    raw_architecture = json.dumps([c.model_dump() for c in architecture], indent=4)
    conversation.add_user(f"Architecture:\n{raw_architecture}")
    conversation.add_user(
        "Available GCP infrastructure:\n- Cloud SQL.\n- External HTTP requests."
    )
    conversation.add_user(f"User story: {user_story}")
    while True:
        next = llm.stream_next(
            conversation,
            tools=[AddComponent.tool()],
        )

        if isinstance(next, llm.RawFunctionParams):
            conversation.add_raw_tool(next)
            components = AddComponent.parse_arguments(next)
            for component in components:
                architecture.append(component)
            raw_architecture = json.dumps(
                [a.model_dump() for a in architecture], indent=4
            )
            conversation.add_tool_response(raw_architecture)
            config["architecture"] = [
                ImplementedComponent(base=c) for c in architecture
            ]
            save_config(config)
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
        initial_config["architecture"] = [
            ImplementedComponent(base=c) for c in initial_config["architecture"]
        ]
        save_config(initial_config)
    config = load_config(args.app)

    user_story = user_input("user story: ")

    run(config, user_story)
