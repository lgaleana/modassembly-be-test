import argparse
import json
import os
from typing import Any, Dict, Tuple
from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.architecture import (
    Component,
    ImplementedComponent,
    load_config,
    save_config,
)
from utils.io import print_system, user_input
from utils.state import Conversation
from workflows.helpers import (
    REPOS,
    extract_json,
    build_graph,
    create_app,
    visualize_graph,
)


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
            "type": "dbmodel",
            "name": "The name of the dbmodel",
            "namespace": "The virtual location of the dbmodel. Use a dot notation.",
            "fields": [
                {{
                    "name": "The name of the field",
                    "purpose": "What the field is used for, important attributes, etc."
                }}
            ],
            "dependencies": ["The other namespace.dbmodels that this model is associated with"],
            "pypi_packages": ["The pypi packages that the dbmodel will need"]
        }},
        "file": Whether the dbmodel has been implemented in code, in a file
    }},
    {{
        "base": {{
            "type": "function",
            "name": "The name of the function",
            "namespace": "The virtual location of the function. Use a dot notation.",
            "purpose": "What the function does, step by step. Ie: 1) ... 2) ...",
            "dependencies": ["The other namespace.functions or namespace.dbmodels that this function uses internally"]
            "is_endpoint": true or false whether this is a FastAPI endpoint
            "pypi_packages": ["The pypi packages that the function will need"]
        }},
        "file": Whether the function has been implemented in code, in a file
    }},
    ...
]
```

There are 2 types of "base" components: dbmodels and functions. A base component can be added if it doesn't already exist in the architecture. And it can only be updated if it hasn't been implemented in a file. To update a component with an implemented file, the user must update it manually.

You will also be given the set of GCP infrastructure that you have access to.

Follow the user's instructions to build the architecture by adding or updating base components. To add or update a component, use the following format:

```json
{{
    "type": "dbmodel" or "function",
    # Attributes of the dbmodel or function
}}
```

Use a modular and composable design pattern. Too many steps in a function's purpose probably means that you should break it apart. Prefer functions over classes. Always prefer the most simple design."""
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

    response = llm.stream_text(conversation)
    conversation.add_assistant(response)
    jsons = extract_json(response)

    for json_ in jsons:
        component = Component.model_validate(json_)

        if component.key in architecture and architecture[component.key].file:
            raise ValueError(
                f"Unable to update component :: {component.key} "
                "because it already has a file associated with it. "
                "Please try again."
            )
        elif "modassembly" in component.key:
            raise ValueError(
                f"Unable to update component :: {component.key} "
                f"because `modassembly` is reserved for internal use. "
                "Use a different namespace. Please try again."
            )
        for dependency in component.root.dependencies:
            if dependency not in architecture:
                raise ValueError(
                    f"Unable to update component :: {component.key} "
                    f"because the `dependency` :: {dependency} doesn't exist in the architecture. "
                    "Make sure to reference models that exist in the architecture. "
                    "Please try again."
                )
        architecture[component.key] = ImplementedComponent(base=component)

    config["architecture"] = list(architecture.values())
    conversation.persist(app_name=app_name)
    save_config(config)
    return config, conversation


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    parser.add_argument("--infra", nargs="+", default=["http", "database"])
    args = parser.parse_args()

    if not os.path.exists(f"{REPOS}/{args.app}"):
        create_app(args.app, args.infra)
    config, _ = run(args.app, user_input("user: "))

    graph = build_graph(config["architecture"])
    visualize_graph(graph)
