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
    description = "Adds or updates one sqlalchemymodel or function of the architecture."


def run(app_name: str, user_message: str) -> Tuple[Dict[str, Any], Conversation]:
    config = load_config(app_name)
    conversation = Conversation.load(app_name)
    architecture = {c.base.root.key: c for c in config["architecture"]}

    if len(conversation) == 0:
        conversation = Conversation()
        conversation.add_system(
            """You are helpful AI assistant that designs backend architectures.

The architecture that you're working with is a python module that will be hosted on Cloud Run as a FastAPI. It's represented as a json in the following format:
```json
[
    {{
        "base": {{
            "type": "sqlalchemymodel",
            "name": "The name of the sqlalchemymodel",
            "namespace": "The virtual location of the sqlalchemymodel. Use a dot notation.",
            "fields": [
                {{
                    "name": "The name of the field",
                    "purpose": "What the field is used for, important attributes, etc."
                }}
            ],
            "associations": ["The other namespace.sqlalchemymodels that this model is associated with"],
            "pypi_packages": ["The pypi packages that the sqlalchemymodel will need"]
        }},
        "file": Whether the sqlalchemymodel has been implemented in code, in a file
    }},
    {{
        "base": {{
            "type": "function",
            "name": "The name of the function",
            "namespace": "The virtual location of the function. Use a dot notation.",
            "purpose": "What the function does, step by step. Ie: 1) ... 2) ...",
            "uses": ["The other namespace.functions or namespace.sqlalchemymodels that this function uses internally"]
            "is_endpoint": true or false whether this is a FastAPI endpoint
            "pypi_packages": ["The pypi packages that the function will need"]
        }},
        "file": Whether the function has been implemented in code, in a file
    }},
    ...
]
```

There are 2 types of "base" components: sqlalchemymodels and functions. A base component can be added if it doesn't already exist in the architecture. And it can only be updated if it hasn't been implemented in a file. To update a component with an implemented file, the user must update it manually.

You will also be given the set of GCP infrastructure that you have access to.

Follow the user's instructions to build the architecture by adding or updating base components. Use a modular and composable design pattern. Too many steps in a function's purpose probably means that you should break it apart. Prefer functions over classes. Always prefer the most simple design."""
        )

        raw_architecture = json.dumps(
            [c.model_dump() for c in architecture.values()], indent=4
        )
        conversation.add_user(
            f"Initial architecture:\n\n{raw_architecture}\n"
            "IMPORTANT: The modassembly namespace is reserved. Use a different one.\n\n"
            f"Available GCP infrastructure: " + str(config["external_infrastructure"])
        )
    conversation.add_user(user_message)

    while True:
        next = llm.stream_next(
            conversation,
            tools=[UpdateComponent.tool()],
        )

        if isinstance(next, llm.RawFunctionParams):
            conversation.add_raw_tool(next)
            components = UpdateComponent.parse_arguments(next)

            valid_components = []
            invalid_components = {}
            for component in components:
                if component.key in architecture and architecture[component.key].file:
                    invalid_components[component.key] = (
                        f"Unable to update component :: {component.key} "
                        "because it already has a file associated with it. "
                        "Please try again."
                    )
                elif "modassembly" in component.key:
                    invalid_components[component.key] = (
                        f"Unable to update component :: {component.key} "
                        f"because `modassembly` is reserved for internal use. "
                        "Use a different namespace. Please try again."
                    )
                elif component.root.type == "sqlalchemymodel":
                    for association in component.root.associations:
                        if association not in architecture:
                            invalid_components[component.key] = (
                                f"Unable to update component :: {component.key} "
                                f"because the `association` :: {association} doesn't exist in the architecture. "
                                "Make sure to reference models that exist in the architecture. "
                                "Please try again."
                            )
                else:
                    for use in component.root.uses:
                        if use not in architecture:
                            invalid_components[component.key] = (
                                f"Unable to update component :: {component.key} "
                                f"because the `use` :: {use} doesn't exist in the architecture. "
                                "Make sure to reference functions that exist in the architecture. "
                                "Please try again."
                            )
                if component.key not in invalid_components:
                    valid_components.append(component)

            for component in valid_components:
                architecture[component.key] = ImplementedComponent(base=component)
            config["architecture"] = list(architecture.values())
            print_system(f"Invalid components: {invalid_components}")

            raw_architecture = json.dumps(
                [c.model_dump() for c in architecture.values()], indent=4
            )
            if not invalid_components:
                tool_response = f"Done. Architecture:\n\n{raw_architecture}"
            else:
                tool_response = (
                    f"Architecture:\n\n{raw_architecture}\n\n"
                    + "\n".join(invalid_components.values())
                )
            conversation.add_tool_response(tool_response)
        else:
            conversation.add_assistant(next)
            conversation.persist(app_name=app_name)
            save_config(config)
            return config, conversation


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    parser.add_argument("--infra", nargs="+", default=["http", "database"])
    args = parser.parse_args()

    if not os.path.exists(f"{REPOS}/{args.app}"):
        os.mkdir(f"{REPOS}/{args.app}")
        create_initial_config(args.app, args.infra)
        Conversation().persist(app_name=args.app)

    config, _ = run(args.app, user_input("user: "))

    graph = build_graph(config["architecture"])
    visualize_graph(graph)
