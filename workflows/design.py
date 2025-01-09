import argparse
import os
from typing import Any, Dict, List, Literal, Tuple, Union

from dotenv import load_dotenv
from pydantic import BaseModel

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
    PatternNotFoundError,
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


class ComponentToUpdate(BaseModel):
    action: Literal["add", "update", "remove"]
    base: Union[Component, str]


def delete_file_for_key(key: str, user: str, app_name: str) -> None:
    file_path = key.replace(".", "/") + ".py"
    file_path = f"{REPOS}/{user}_{app_name}/{file_path}"
    if os.path.exists(file_path):
        os.remove(file_path)


def run(
    app_name: str,
    user_message: str,
    user: str,
) -> Tuple[Dict[str, Any], Conversation]:
    config = load_config(app_name, user)
    conversation = Conversation.load(app_name, user)

    architecture = {c.design.root.key: c for c in config["architecture"]}
    save_config(config)

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
        "is_deployed": true or false whether the dbmodel has been implemented and deployed
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
         "is_deployed": true or false whether the function has been implemented and deployed
    }},
    ...
]
```

Think of this architecture as lego blocks that you can compose together. Use a modular design pattern. Too many steps in a function's purpose probably means that you should break it apart. Always prefer the most simple design.

Work with the user to build the architecture by adding, updating or removing components. To add or update a component, use the following format:

```json
{{
    "action": "add", "update" or "remove",
    "type": "dbmodel" or "function",
    # Attributes of the dbmodel or function
}}
```

To remove a component, use the following format:

```json
{{
    "action": "remove",
    "name": "The name of the function to remove"
    "namespace": "The namespace of the function to remove"
}}
```

To refactor a component, it might be necessary to first remove it and then add it again.

There are two types of "design" components: dbmodels and functions. functions can be added, updated or removed at any time. However, dbmodels can only be added, updated or removed if they haven't been deployed yet. Updating production database models is not straightforward. To update or remove a dbmodel, the user must do it manually. The modassembly namespace is reserved. You can't add or update components in this namespace.

At some point, the architecture will be implemented into actual code (you don't have access to that code). The order of implementation will be guided by the `"dependencies"` attribute. It's VERY IMPORTANT that you keep this attribute updated."""
        )

    conversation.add_system(
        f"Current architecture:\n\n{present_to_llm(list(architecture.values()))}\n\n"
        "VERY IMPORTANT: Update the dependencies."
    )
    conversation.add_user(user_message)

    attempts = 0
    components_to_update = {}
    while True:
        attempts += 1
        response = llm.stream_text(conversation)
        conversation.add_assistant(response)
        try:
            jsons = extract_json(response)
        except PatternNotFoundError as e:
            jsons = []

        try:
            for json_ in jsons:
                if isinstance(json_, List):
                    for j in json_:
                        jsons.append(j)
                    continue

                if "action" in json_:
                    action = json_["action"]
                    key = (
                        json_["namespace"] + "." + json_["name"]
                        if json_["namespace"]
                        else json_["name"]
                    )
                    if key.startswith("modassembly") or key.startswith("main"):
                        raise ValueError(
                            f"Unable to {action} component :: {key} "
                            f"because it's reserved for internal use. "
                            "Please try again."
                        )
                    if action in [Action.UPDATE, Action.REMOVE]:
                        if key not in architecture:
                            raise ValueError(
                                f"Unable to {action} component :: {key} "
                                "because the component doesn't exist in the architecture. "
                                "Please try again."
                            )
                    if (
                        key in architecture
                        and isinstance(architecture[key].design, DBModel)
                        and architecture[key].is_deployed
                    ):
                        raise ValueError(
                            f"Unable to {action} dbmodel :: {key} "
                            "because the dbmodel has already been implemented."
                        )
                    if action in [Action.ADD, Action.UPDATE]:
                        component = Component.model_validate(json_)
                        for dependency in component.root.dependencies:
                            if (
                                dependency not in architecture
                                and dependency not in components_to_update
                            ):
                                raise ValueError(
                                    f"Unable to {action} component :: {component.key} "
                                    f"because the `dependency` :: {dependency} doesn't exist in the architecture. "
                                    "Make sure to reference models that exist in the architecture. "
                                    "Please try again."
                                )
                        components_to_update[component.key] = ComponentToUpdate(
                            action=action, base=component
                        )
                    else:
                        components_to_update[key] = ComponentToUpdate(
                            action=action, base=key
                        )
                else:
                    implemented_component = ImplementedComponent.model_validate(json_)
                    if not implemented_component.design.key.startswith(
                        "modassembly"
                    ) and not implemented_component.design.key.startswith("main"):
                        conversation.add_system(
                            f"Will remove and add :: {implemented_component.design.key}."
                            "\n\nRemember to user add/update/remove operations."
                        )
                        jsons.append(
                            {
                                "action": Action.REMOVE,
                                "name": implemented_component.design.root.name,
                                "namespace": implemented_component.design.root.namespace,
                            }
                        )
                        jsons.append(
                            {
                                "action": Action.ADD,
                                **implemented_component.design.model_dump(),
                            }
                        )
                    else:
                        conversation.add_system(
                            f"{implemented_component.design.key} won't be updated "
                            "because it's reserved for internal use."
                        )
        except ValueError as e:
            if attempts == 3:
                components_to_update = {}
                raise e
            print_system(f"{type(e).__name__}({str(e)})")
            conversation.add_system(f"{type(e).__name__}({str(e)})")
            continue

        for component in components_to_update.values():
            if component.action == Action.REMOVE:
                del architecture[component.base]
                delete_file_for_key(component.base, user, app_name)
            else:
                architecture[component.base.key] = ImplementedComponent(
                    design=component.base
                )
                delete_file_for_key(component.base.key, user, app_name)
        config["architecture"] = list(architecture.values())
        conversation.persist(app_name, user)
        save_config(config)
        return config, conversation


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    parser.add_argument("--infra", nargs="+", default=["www", "sql"])
    args = parser.parse_args()

    if not os.path.exists(f"{REPOS}/{args.app}"):
        create_app(args.app, args.infra, "")
    config, _ = run(args.app, user_input("user: "), "")

    graph = build_graph(config["architecture"])
    visualize_graph(graph)
