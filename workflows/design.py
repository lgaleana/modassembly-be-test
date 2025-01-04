import argparse
import json
import os
from typing import Any, Dict, List, Tuple
from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.architecture import (
    Component,
    ImplementedComponent,
    load_config,
    present_to_llm,
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
    architecture = {c.design.root.key: c for c in config["architecture"]}

    if len(conversation) == 0:
        conversation = Conversation()
        conversation.add_system(
            """You are helpful AI assistant that designs backend architectures.

The architecture that you're working with is a python module that will be hosted on Cloud Run as a FastAPI. It's represented as a json in the following format:

```json
[
    {{
        "type": "dbmodel",
        "name": "The name of the dbmodel",
        "namespace": "The virtual location of the dbmodel. Use a dot notation.",
        "fields": [
            {{
                    "name": "The name of the field",
                    "purpose": "What the field is used for, important remarks, etc."
            }}
        ],
        "dependencies": ["The other namespace.dbmodels that the model is associated with"],
        "pypi_packages": ["The pypi packages that the dbmodel will need"]
    }},
    {{
        "type": "function",
        "name": "The name of the function",
        "namespace": "The virtual location of the function. Use a dot notation.",
        "purpose": "What the function does, step by step. Ie: 1) ... 2) ...",
        "dependencies": ["The other namespace.functions or namespace.dbmodels that the actual code of this function depends on"]
        "is_endpoint": true or false whether this is a FastAPI endpoint
        "pypi_packages": ["The pypi packages that the function will need"]
    }},
    ...
]
```

Follow the user's instructions to build the architecture by adding or updating design components. To add or update a component, use the following format:

```json
{{
    "type": "dbmodel" or "function",
    # Attributes of the dbmodel or function
}}
```

There are 2 types of "design" components: dbmodels and functions. Your job is to design an architecture that better describes what the user wants to do. At some point, the architecture will be implemented into actual code. The order of implementation will be guided by the `"dependencies"` attribute. It's VERY IMPORTANT that you keep this attribute up to date.

Use a modular and composable design pattern. Too many steps in a function's purpose probably means that you should break it apart. Always prefer the most simple design. At every step, think whether the architecture that you're describing is the best one for what the user wants to do. If not, make the necessary changes."""
        )

        conversation.add_user(
            f"Initial architecture:\n\n{present_to_llm(list(architecture.values()))}\n"
            "IMPORTANT: The modassembly namespace is reserved. "
            "You can't add or update components in this namespace."
        )
    conversation.add_user(user_message)

    while True:
        response = llm.stream_text(conversation)
        conversation.add_assistant(response)
        jsons = extract_json(response)

        try:
            for json_ in jsons:
                if isinstance(json_, List):
                    for j in json_:
                        jsons.append(j)
                    continue
                component = Component.model_validate(json_)

                if "modassembly" in component.key:
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
                architecture[component.key] = ImplementedComponent(design=component)
        except ValueError as e:
            print_system(e)
            conversation.add_system(str(e))
            continue

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
