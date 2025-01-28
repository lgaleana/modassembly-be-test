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
    Function,
    ImplementedComponent,
    Infrastructure,
    load_config,
    save_config,
)
from utils.config.initial import AVAILABLE_INFRASTRUCTURE
from utils.io import print_system
from utils.state import Conversation
from workflows.brainstorm import PROMPT
from workflows.helpers import (
    PatternNotFoundError,
    extract_json,
)


class Action:
    UPDATE = "update"
    REMOVE = "remove"


class ComponentToUpdate(BaseModel):
    action: Literal["update", "remove"]
    key: str
    base: Optional[Component]


def present_to_llm(architecture: List[ImplementedComponent]) -> str:
    return json.dumps([c.design.model_dump() for c in architecture], indent=4)


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
    }},
    {{
        "type": "datamodel",
        "name": "The name of the datamodel",
        "namespace": "The virtual location of the code, ie, the file path. Use a dot notation.",
        "fields": [
            {{
                    "name": "The name of the field",
                    "purpose": "What the field is used for, important remarks, etc."
            }}
        ],
        "dependencies": ["The other namespace.datamodels that the model is associated with."],
        "pypi_packages": ["The pypi packages that the datamodel will need."]
    }},
    {{
       "type": "function",
        "name": "The name of the function",
        "namespace": "The virtual location of the code, ie, the file path.. Use a dot notation.",
        "purpose": "Detailed description of what the function does, step by step. Ie: 1) ...\n2) ...Mention every important remark.",
        "dependencies": ["The other namespace.functions or namespace.datamodels that the code depends on."],
        "pypi_packages": ["The pypi packages that the function will need."],
        "is_endpoint": true or false whether this is a FastAPI endpoint
    }}
    ...
]
```

Work with the user to add/update/remove components. To add or update a component, use the following format:

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

There are three types of components: infrastructures, datamodels and functions.

Infrastructure represents the GCP infrastructure. As you add infrastructure, utility functions will be added for you so that your application can connect to it. You can skip adding them. Available infrastructure:

```json
{INFRASTRUCTURE}
```

Think of data models as data sinks. To add datamodels you must first have the external infrastructure to support it.

functions represent the business logic. They will be executed on Google Cloud Run as a FastAPI. Use python naming conventions.

`app.main` and `app.modassembly` are reserved for internal use. You can't update them. Avoid circular dependencies."""


def run(
    app_name: str,
    user: str,
    user_message: str,
) -> Tuple[Dict[str, Any], Conversation]:
    config = load_config(app_name, user)
    conversation = Conversation.load(app_name, user, name="conversation_architecture")

    architecture = {c.design.root.key: c for c in config["architecture"]}

    if len(conversation) == 0:
        conversation = Conversation()
        conversation.add_system(PROMPT)

    conversation.remove_last_message_type("architecture")
    conversation.remove_last_message_type("instruction")
    conversation.add_system(
        f"Current logic:\n\n{present_to_llm(list(architecture.values()))}",
        type_="architecture",
    )
    conversation.add_system(
        """Your goal is to interpret the user's requests and add/update/remove components to design the architecture that makes the most sense.
        
Example: for a message that looks like: "Add an endpoint that does X, Y and Z", consider the complexity of each step. Consider whether X, Y and Z should be functions. functions should map to less than 100 lines of code. Then, add/update/remove components in the following order:

1. Less dependent
2. More dependent
...
N. Endpoint

Remember to update the upstream dependencies. To rename or move a component, first remove it and add it again. Be brief.""",
        type_="instruction",
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
            conversation.add_system(f"ERROR :: {e}\n\nSkipping all changes.")
            conversation.add_user("There was an error. Please try again.")
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
                        if isinstance(component.root, DataModel) or isinstance(
                            component.root, Function
                        ):
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
            conversation.add_system(f"ERROR :: {e}\n\nNo changes applied.")
            conversation.add_user("There was an error. Try again.")
            continue

        for component in components_to_update.values():
            if component.action == Action.REMOVE:
                architecture[component.key].update_status = "to_remove"
            else:
                architecture[component.key] = ImplementedComponent(
                    design=component.base
                )
                if isinstance(component.base, Infrastructure):
                    architecture[component.key].update_status = "up_to_date"
                else:
                    architecture[component.key].update_status = "to_update"
        config["architecture"] = list(architecture.values())
        save_config(config)
        conversation.remove_all_message_type("instruction")
        conversation.persist(app_name, user, name="conversation_architecture")

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

        return config, conversation
