import argparse
import json
import os
from typing import Any, Dict, List, Literal, Optional, Tuple

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from ai import llm
from app.logging.log_user_activity import log_user_activity
from utils.config.architecture import (
    Component,
    DataModel,
    ImplementedComponent,
    Infrastructure,
    load_config,
    present_to_llm,
    save_config,
)
from utils.config.initial import AVAILABLE_INFRASTRUCTURE
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
    key: str
    base: Optional[Component]


def delete_file_for_key(key: str, user: str, app_name: str) -> None:
    file_path = key.replace(".", "/") + ".py"
    file_path = f"{REPOS}/{user}_{app_name}/{file_path}"
    if os.path.exists(file_path):
        os.remove(file_path)


PROMPT = """You are helpful AI assistant that designs backend architectures.

The entire architecture will be hosted on Google Cloud Platform. The core of the business logic (datamodels and functions) is a python service that will be hosted on Cloud Run as a FastAPI. The architecture is represented as a json in the following format:

```json
[
    {{
        "type": "infrastructure",
        "name": "The name of the infrastructure",
        "namespace" = "External" (only valid value)
    }},
    {{
        "type": "datamodel",
        "name": "The name of the datamodel",
        "namespace": "The virtual location of the code. Use a dot notation.",
        "fields": [
            {{
                    "name": "The name of the field",
                    "purpose": "What the field is used for, important remarks, etc."
            }}
        ],
        "dependencies": ["The other namespace.datamodels that the model is associated with"],
        "pypi_packages": ["The pypi packages that the datamodel will need"]
    }},
    {{
       "type": "function",
        "name": "The name of the function",
        "namespace": "The virtual location of the code. Use a dot notation.",
        "purpose": "What the function does, step by step. Ie: 1) ... 2) ... Each step is equivalent to a couple lines of code.",
        "dependencies": ["The other namespace.functions that the code depends on"],
        "pypi_packages": ["The pypi packages that the function will need"],
        "is_endpoint": true or false whether this is a FastAPI endpoint
    }}
    ...
]
```

Work with the user to build the architecture by adding, updating or removing components. To add or update a component, use the following format:

```json
{{
    "action": "add" or "update",
    "type": "infrastructure", "datamodel" or "function",
    # Attributes of the infrastructure, datamodel or function
}}
```

To remove a component, use the following format:

```json
{{
    "action": "remove",
    "name": "The name of the component to remove"
    "namespace": "The namespace of the component"
}}
```

As you generate the json, it will be extracted and the component will be added/updated/removed to/from the architecture. So there is no need to ask for confirmation. Act as if the change has already been applied.

There are three types of "design" components: infrastructures, datamodels and functions.

Think of datamodels as data sinks. They mostly represent database tables but they could represent any kind of tabular data. To add datamodels you must have the external infrastructure to support it first.

At some point, every component will be implemented into actual code (you don't have access to that code). All of it will be executed on Google Cloud Run, except for the infrastructures. Cloud Run is a servelerss container desgined for web applications. More complex infrastructure has to be run seperately. "infrastructure" represents all the external infrastructure that is part of your backend architecture but that won't be run on Cloud Run. Nonetheless, Cloud Run has access to it. It's analogous to the GCP infrastructure.

What this means is that you must be careful about how you design your business logic. Keep it within the limitations of a web service. For anything else, rely on the available external infrastructure. As you add infrastructure, utility functions will be added so that your application can connect to it. Add the infrastructure first; then, the functionality.

functions represent the business logic. The main goal is to design an architecture that is malleable, easy to refactor and easy to maintain. You will accomplish this by using modularity and the single responsibility principle. Each function should do one thing. No function should be mapped to more than 100 lines of code.

The `"dependencies"` attribute is VERY IMPORTANT. When each component is implemented into code, the order of implementation will be guided by it. Always update it."""


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
        conversation.add_system(PROMPT)
        raw_infrastructure = json.dumps(
            [
                {
                    "name": i["name"],
                    "namespace": i["namespace"],
                    "utility_functions": [
                        c.model_dump() for c in i["utility_functions"]
                    ],
                }
                for i in AVAILABLE_INFRASTRUCTURE
            ],
            indent=4,
        )
        conversation.add_system(
            "The following infrastructure is available for you "
            f"to add to the architecture:\n\n{raw_infrastructure}\n\n"
            "`app.main` is reserved for internal use. You can't update it."
        )

    conversation.remove_last_message_type("architecture")
    conversation.add_system(
        f"Current architecture:\n\n{present_to_llm(list(architecture.values()))}\n\n"
        "Keep the business logic within the limitations of a web service.\n"
        "To rename or move a component, first remove it and add it again.\n"
        "VERY IMPORTANT: When updating a component, update all of its occurrence accross the architecture.",
        type_="architecture",
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
        except Exception as e:
            if attempts == 3:
                components_to_update = {}
                raise e
            print_system(f"{type(e).__name__}({str(e)})")
            conversation.add_system(f"{type(e).__name__}({str(e)})")
            continue

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
                    if key == "app.main":
                        raise ValueError(
                            f"Unable to {action} component :: {key} "
                            f"because it's reserved for internal use. "
                            "You can't update it. Please try again."
                        )
                    if action in [Action.UPDATE, Action.REMOVE]:
                        if key not in architecture:
                            raise ValueError(
                                f"Unable to {action} component :: {key} "
                                "because the component doesn't exist in the architecture. "
                                "Please try again."
                            )
                    if action in [Action.ADD, Action.UPDATE]:
                        component = Component.model_validate(json_)
                        if (
                            isinstance(component.root, DataModel)
                            and "External.SQLDatabase" not in architecture
                            and "External.FileStorage" not in architecture
                            and "External.SQLDatabase" not in components_to_update
                            and "External.FileStorage" not in components_to_update
                        ):
                            raise ValueError(
                                f"Unable to {action} component :: {key} "
                                "because there is no infrastructure to support it. "
                                "Please add the proper infrastructure first."
                            )
                        component.root.dependencies = [
                            (
                                "app." + dependency
                                if not dependency.startswith("External")
                                and not dependency.startswith("app.")
                                else dependency
                            )
                            for dependency in component.root.dependencies
                        ]
                        for dependency in component.root.dependencies:
                            if (
                                dependency not in architecture
                                and dependency not in components_to_update
                            ):
                                raise ValueError(
                                    f"Unable to {action} component :: {component.key} "
                                    f"because the `dependency` :: {dependency} doesn't exist in the architecture. "
                                    "Add components in the order of their dependencies. "
                                    "Please try again."
                                )
                        if isinstance(component.root, Infrastructure):
                            for infra in AVAILABLE_INFRASTRUCTURE:
                                if infra["name"] == component.root.name:
                                    utility_functions = infra["utility_functions"]
                                    for function_ in utility_functions:
                                        components_to_update[function_.key] = (
                                            ComponentToUpdate(
                                                action=Action.ADD,
                                                key=function_.key,
                                                base=function_,
                                            )
                                        )
                                    break
                        if not isinstance(
                            component.root, Infrastructure
                        ) and not component.root.namespace.startswith("app."):
                            component.root.namespace = "app." + component.root.namespace
                            conversation.add_system("Prefixing namespace with `app.`")
                        components_to_update[component.key] = ComponentToUpdate(
                            action=action, key=component.key, base=component
                        )
                    else:
                        components_to_update[key] = ComponentToUpdate(
                            action=action, key=key, base=None
                        )
                else:
                    component = Component.model_validate(json_)
                    if not component.key == "app.main":
                        conversation.add_system(
                            f"Will remove and add :: {component.key}."
                            "\n\nRemember to user add/update/remove operations."
                        )
                        jsons.append(
                            {
                                "action": Action.REMOVE,
                                "name": component.root.name,
                                "namespace": component.root.namespace,
                            }
                        )
                        jsons.append(
                            {
                                "action": Action.ADD,
                                **component.model_dump(),
                            }
                        )
                    else:
                        conversation.add_system(
                            f"{component.key} won't be updated "
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
                del architecture[component.key]
                delete_file_for_key(component.key, user, app_name)
            else:
                architecture[component.key] = ImplementedComponent(
                    design=component.base
                )
                architecture[component.key].file = None
                delete_file_for_key(component.key, user, app_name)
        config["architecture"] = list(architecture.values())
        conversation.persist(app_name, user)
        save_config(config)

        if user != "lgaleana":
            log_user_activity(
                user,
                "design",
                {
                    "config": {
                        "name": config["name"],
                        "user": config["user"],
                        "architecture": [
                            c.model_dump() for c in config["architecture"]
                        ],
                        "github": config["github"],
                        "url": config["url"],
                    },
                    "conversation": conversation,
                },
            )

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
