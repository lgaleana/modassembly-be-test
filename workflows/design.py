import argparse
import json
import os
from typing import Any, Dict, Tuple
from dotenv import load_dotenv

load_dotenv()

from ai import llm
from ai.function_calling import Function
from utils.architecture import (
    Component,
    ImplementedComponent,
    create_initial_config,
    load_config,
    save_config,
)
from utils.io import print_system, user_input
from utils.state import Conversation
from workflows.helpers import REPOS, build_graph, visualize_graph


class UpdateComponent(Function[Component]):
    description = "Adds or updates a sqlalchemymodel or function to the architecture."


def run(config: Dict[str, Any], user_story: str) -> Tuple[str, Dict[str, Any]]:
    architecture = {c.base.root.key: c for c in config["architecture"]}

    if not config["conversation"]:
        conversation = Conversation()
        conversation.add_system(
            """You are helpful AI assistant that designs backend architectures.

    You will be given the backend architecture of a python module that is hosted on Cloud Run as a FastAPI. The architecture will be represented as a json in the following format:
    ```json
    [
        {{
            "base": {{
                "type": "sqlalchemymodel",
                "name": "The name of the sqlalchemymodel",
                "namespace": "The namespace of the sqlalchemymodel",
                "fields": ["The fields of the sqlalchemymodel"],
                "associations": ["The other sqlalchemymodels that this model is associated with"],
                "pypi_packages": ["The pypi packages that it will need"],
            }},
            "file": null
        }},
        {{
            "base": {{
                "type": "function",
                "name": "The name of the function",
                "namespace": "The namespace of the function",
                "purpose": "What the component does",
                "uses": ["The other namespace.functions or namespace.sqlalchemymodels that this component uses internally."],
                "pypi_packages": ["The pypi packages that it will need"],
                "is_endpoint": true or false whether this is a FastAPI endpoint
            }},
            "file": null
        }},
        ...
    ]
    ```

    There are 2 types of "base" components: sqlalchemymodels and functions. A component can be added if it doesn't already exist in the architecture. And it can only be updated if it doesn't have a file associated with it. To update a component with an implemented file, the user must update it manually.

    You will also be given the set of GCP infrastructure that you have access to.
    Given an user story, build the architecture by adding base components.
    Always prefer the most simple design."""
        )

        raw_architecture = json.dumps(
            [c.model_dump() for c in architecture.values()], indent=4
        )
        conversation.add_user(f"Architecture:\n{raw_architecture}")
        conversation.add_user(
            "Available GCP infrastructure:\n- Cloud SQL.\n- External HTTP requests."
        )
    else:
        conversation = Conversation(config["conversation"])
    config["conversation"] = conversation
    conversation.add_user(user_story)

    assistant_message = None
    valid_components = []
    while True:
        next = llm.stream_next(
            conversation,
            tools=[UpdateComponent.tool()],
        )

        if isinstance(next, llm.RawFunctionParams):
            conversation.add_raw_tool(next)
            components = UpdateComponent.parse_arguments(next)

            invalid_components = []
            for component in components:
                if not component.key in architecture:
                    valid_components.append(component)
                elif architecture[component.key].file is None:
                    valid_components.append(component)
                else:
                    invalid_components.append(component)

            if len(components) > len(invalid_components):
                tool_response = f"Done.\n"
                if invalid_components:
                    tool_response += (
                        "However, the following components were not updated "
                        f"because they already have a file associated with them: "
                        f"{', '.join(c.key for c in invalid_components)}"
                    )
            else:
                tool_response = "Unable to update any components because they already have a file associated with them."
            print_system(f"Invalid components: {invalid_components}")
            raw_architecture = json.dumps(
                [c.model_dump() for c in architecture.values()], indent=4
            )
            tool_response += f"\n\nArchitecture:\n{raw_architecture}"
            conversation.add_tool_response(tool_response)

            for component in valid_components:
                architecture[component.key] = ImplementedComponent(base=component)
            config["architecture"] = list(architecture.values())
            save_config(config)
        else:
            save_config(config)
            return next, config


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    if not os.path.exists(f"{REPOS}/{args.app}"):
        os.mkdir(f"{REPOS}/{args.app}")
        create_initial_config(args.app)
    config = load_config(args.app)

    user_story = user_input("user story: ")

    _, config = run(config, user_story)

    graph = build_graph(config["architecture"])
    visualize_graph(graph)
