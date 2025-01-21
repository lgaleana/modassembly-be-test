import json
import os
from typing import Any, Dict, List, Literal, Optional

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
from utils.io import print_system
from utils.state import Conversation
from workflows.brainstorm import PROMPT
from workflows.helpers import (
    PatternNotFoundError,
    REPOS,
    extract_json,
)


class Action:
    UPDATE = "update"
    REMOVE = "remove"


class ComponentToUpdate(BaseModel):
    action: Literal["update", "remove"]
    key: str
    base: Optional[Component]


def delete_file_for_key(key: str, user: str, app_name: str) -> None:
    file_path = key.replace(".", "/") + ".py"
    file_path = f"{REPOS}/{user}_{app_name}/{file_path}"
    if os.path.exists(file_path):
        os.remove(file_path)


INFRASTRUCTURE = json.dumps(
    [
        {
            "name": i["name"],
            "namespace": i["namespace"],
            "description": i["description"],
            "added_functions": [c.model_dump() for c in i["added_functions"]],
        }
        for i in AVAILABLE_INFRASTRUCTURE
    ],
    indent=4,
)


PROMPT = f"""You are helpful AI assistant that designs distributed backend systems.

The entire system will be hosted on Google Cloud Platform. The architecture is represented as a json in the following format:

```json
[
    {{
        "type": "infrastructure",
        "name": "The name of the infrastructure",
        "namespace" = "External" (only valid value)
        "config": {{"The configuration of the infrastructure"}}
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
        "dependencies": ["The other namespace.functions or namespace.datamodels that the code depends on"],
        "pypi_packages": ["The pypi packages that the function will need"],
        "is_endpoint": true or false whether this is a FastAPI endpoint
    }}
    ...
]
```

Follow the user's instructions by adding, updating or removing components. To add or update a component, use the following format:

```json
{{
    "action":"update",
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

To rename or move a component, first remove it and add it again.

There are three types of components: infrastructures, datamodels and functions.

Infrastructure represent the GCP infrastructure.

At some point, data models and functions will be implemented into actual code (you don't have access to that code). They will be executed on Google Cloud Run as a FastAPI. Cloud Run is a servelerss container desgined for web applications. What this means is that you must be careful about how you design your business logic. Keep it within the limitations of a web service. For anything else, rely on the other infrastructure. Available infrastructure:

```json
{INFRASTRUCTURE}
```

Think of data models as data sinks. They represent database tables.

Functions represent the business logic. The main goal is to design an architecture that is malleable, easy to refactor and easy to maintain. You will accomplish this by using modularity and the single responsibility principle. Each function should do only one thing. Functions should map to less than 100 lines of code. Use python naming conventions. `app.main` is reserved for internal use. You can't update it."""


def run(
    app_name: str,
    user: str,
    user_message: str,
) -> Dict[str, Any]:
    config = load_config(app_name, user)
    conversation = Conversation.load(app_name, user, name="conversation_design")

    architecture = {c.design.root.key: c for c in config["architecture"]}

    if len(conversation) == 0:
        conversation = Conversation()
        conversation.add_system(PROMPT)

    conversation.remove_last_message_type("architecture")
    conversation.add_user(
        f"Current architecture:\n\n{present_to_llm(list(architecture.values()))}",
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
                raise e
            components_to_update = {}
            print_system(f"{type(e).__name__}({str(e)})")
            conversation.add_system(
                f"ERROR :: {e}\nSkipped :: " + ", ".join(j["name"] for j in jsons)
            )
            conversation.add_user("There was an error. Update everything again.")
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
                            "You can't update it."
                        )
                    if action != Action.REMOVE:
                        component = Component.model_validate(json_)
                        if (
                            isinstance(component.root, DataModel)
                            and "External.CloudSQL" not in architecture
                            and "External.CloudStorage" not in architecture
                            and "External.CloudSQL" not in components_to_update
                            and "External.CloudStorage" not in components_to_update
                        ):
                            raise ValueError(
                                f"Unable to {action} component :: {key} "
                                "because there is no infrastructure to support it."
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
                                    "Add components in the order of their dependencies."
                                )
                        if isinstance(component.root, Infrastructure):
                            for infra in AVAILABLE_INFRASTRUCTURE:
                                if infra["name"] == component.root.name:
                                    added_functions = infra["added_functions"]
                                    for function_ in added_functions:
                                        components_to_update[function_.key] = (
                                            ComponentToUpdate(
                                                action=Action.UPDATE,
                                                key=function_.key,
                                                base=function_,
                                            )
                                        )
                                        conversation.add_system(
                                            f"Will add :: {function_.key}."
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
                            "\n\nRemember to use update/remove operations."
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
                                "action": Action.UPDATE,
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
                raise e
            components_to_update = {}
            print_system(f"{type(e).__name__}({str(e)})")
            conversation.add_system(
                f"ERROR :: {e}\nSkipped :: " + ", ".join(j["name"] for j in jsons)
            )
            conversation.add_user("There was an error. Update everything again.")
            continue

        for component in components_to_update.values():
            if component.action == Action.REMOVE:
                architecture.pop(component.key, None)
                delete_file_for_key(component.key, user, app_name)
            else:
                architecture[component.key] = ImplementedComponent(
                    design=component.base
                )
                architecture[component.key].file = None
                delete_file_for_key(component.key, user, app_name)
        config["architecture"] = list(architecture.values())
        save_config(config)
        conversation.persist(app_name, user, name="conversation_design")

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
                },
            )

        return config
