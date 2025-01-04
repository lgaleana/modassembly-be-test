import argparse
import os
from typing import Any, Dict, List, Tuple
from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.architecture import (
    Component,
    DBModel,
    ImplementedComponent,
    load_config,
    present_to_llm,
    save_config,
)
from utils.io import print_system, user_input
from utils.state import Conversation
from workflows.helpers import (
    PatternMatchError,
    REPOS,
    extract_json,
    build_graph,
    create_app,
    visualize_graph,
)


class Action:
    ADD = "add"
    UPDATE = "update"
    REMOVE = "remove"


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
        "is_implemented": true or false whether the dbmodel has been implemented in actual code
    }},
    {{
        {{
            "type": "function",
            "name": "The name of the function",
            "namespace": "The virtual location of the function. Use a dot notation.",
            "purpose": "What the function does, step by step. Ie: 1) ... 2) ...",
            "dependencies": ["The other namespace.functions or namespace.dbmodels that the actual code of this function depends on"]
            "is_endpoint": true or false whether this is a FastAPI endpoint
            "pypi_packages": ["The pypi packages that the function will need"]
        }},
         "is_implemented": true or false whether the function has been implemented in actual code
    }},
    ...
]
```

Think of this architecture as lego blocks that you can compose together. Use a modular design pattern. Too many steps in a function's purpose probably means that you should break it apart. Always prefer the most simple design.

Follow the user's instructions to build the architecture by adding, updating or removing components. Use the following format:

```json
{{
    "action": "add", "update" or "remove",
    "type": "dbmodel" or "function",
    # Attributes of the dbmodel or function
}}
```

At some point, the architecture will be implemented into actual code. The order of implementation will be guided by the `"dependencies"` attribute. It's VERY IMPORTANT that you keep this attribute up to date.

There are two types of "design" components: dbmodels and functions. functions can be added, updated or removed at any time. However; dbmodels can only be added, updated or removed if they haven't been implemented yet. To update or remove a dbmodel, the user must do it manually

IMPORTANT: The modassembly namespace is reserved. You can't add or update components in this namespace."""
        )

    conversation.add_user(
        f"Current architecture:\n\n{present_to_llm(list(architecture.values()))}"
    )
    conversation.add_user(user_message)

    attempts = 0
    valid_components = {}
    while True:
        attempts += 1
        response = llm.stream_text(conversation)
        conversation.add_assistant(response)
        try:
            jsons = extract_json(response)
        except PatternMatchError as e:
            if "No matches found for pattern :: ```json\n(.*?)```" in str(e):
                raise e
            jsons = []

        try:
            for json_ in jsons:
                if isinstance(json_, List):
                    for j in json_:
                        jsons.append(j)
                    continue
                component = Component.model_validate(json_)

                action = json_["action"]
                if (
                    isinstance(component.root, DBModel)
                    and component.key in architecture
                ):
                    raise ValueError(
                        f"Unable to {action} dbmodel :: {component.key} "
                        "because dbmodel has already been implemented."
                    )
                if "modassembly" in component.key:
                    raise ValueError(
                        f"Unable to {action} component :: {component.key} "
                        f"because `modassembly` is reserved for internal use. "
                        "Use a different namespace. Please try again."
                    )
                for dependency in component.root.dependencies:
                    if dependency not in architecture:
                        raise ValueError(
                            f"Unable to {action} component :: {component.key} "
                            f"because the `dependency` :: {dependency} doesn't exist in the architecture. "
                            "Make sure to reference models that exist in the architecture. "
                            "Please try again."
                        )
                valid_components[component.key] = component
        except ValueError as e:
            if attempts == 3:
                raise e
            print_system(e)
            conversation.add_system(str(e))
            continue

        for component in valid_components.values():
            if action == Action.ADD or action == Action.UPDATE:
                architecture[component.key] = ImplementedComponent(design=component)
            elif action == Action.REMOVE:
                del architecture[component.key]

        config["architecture"] = list(architecture.values())
        conversation.persist(app_name=app_name)
        save_config(config)
        return config, conversation


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    parser.add_argument("--infra", nargs="+", default=["www", "sql"])
    args = parser.parse_args()

    if not os.path.exists(f"{REPOS}/{args.app}"):
        create_app(args.app, args.infra)
    config, _ = run(args.app, user_input("user: "))

    graph = build_graph(config["architecture"])
    visualize_graph(graph)
