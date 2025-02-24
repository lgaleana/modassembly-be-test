import json
from typing import Any, Dict, List, Literal, Optional, Tuple

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from ai import llm
from utils.config.architecture import (
    Component,
    DataModel,
    ImplementedComponent,
    Infrastructure,
    load_config,
    save_config,
)
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
    action: Literal["add", "update", "remove"]
    key: str
    base: Optional[Component]


def present_to_llm(architecture: List[ImplementedComponent]) -> str:
    return json.dumps(
        [c.design.model_dump() for c in architecture if c.update_status != "to_remove"],
        indent=4,
    )


PROMPT = f"""You are helpful assistant that designs distributed systems.

# Introduction

You are going to write a technical design document as a json in the following format:

[
    {{
        "type": "infrastructure",
        "name": "The name of the infrastructure",
        "config": {{"The details of the infrastructure"}}
    }},
    {{
        "type": "datamodel",
        "name": "The name of the datamodel. Use CamelCase.",
        "namespace": "The virtual location of the datamodel. Use a dot notation. Put it inside app.",
        "fields": [
            {{
                "name": "The name of the field",
                "purpose": "What the field is used for, important remarks, etc."
            }}
        ],
        "dependencies": ["The other namespace.name datamodels that the model is associated with."]
    }},
    {{
       "type": "logic",
        "name": "A name to identify the logic. Use snake_case.",
        "namespace": "The virtual location of the module. Use a dot notation. Put it inside app.",
        "purpose": "A text description of what the logic does. Code will be generated from this field. Mention every important detail.",
        "dependencies": ["The other namespace.name of the datamodels or logic that the code calls internally."],
        "pypi_packages": ["The pypi packages that the code will need, eg, package==version. Reuse existing versions."],
        "is_endpoint": true or false whether this is a FastAPI endpoint
    }}
    ...
]

There are three types of modules: infrastructure, datamodels and logic. infrastructure represents Google Cloud Platform infrastructure that the system has access to. datamodels represent sqlalchemy models. logic represents the business logic. datamodels and logic will be executed on Google Cloud Run as a Python FastAPI.

# Instructions

You have two main jobs:

## Job 1

Interpret the user's requests and add/update/remove datamodels or logic.

To add or update a datamodel or logic, use the following format:

{{
    "action": "add" or "update",
    "type": "datamodel" or "logic",
    # Attributes of the datamodel or logic
}}

When updating an existing module, speak as if you were writing the specification for the first time. Preserve every important and specific detail.

To remove a datamodel or logic, use the following format:

{{
    "action": "remove",
    "name": "The name of the datamodel or logic to remove",
    "namespace": "The namespace of the datamodel or logic"
}}

To rename a module, first remove it and then add it again.

Use the format:

```json
...
```

Use FastAPI design patterns.

## Job 2

Every time that you update a module, check all of its upstream and downstream dependencies. Update every `"purpose"` and `"dependencies"` field as needed.

The entire json must capture:

1. Every technical detail.
2. The complete functionality of the system."""


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
        conversation.add_developer(PROMPT)

    conversation.remove_last_message_type("architecture")
    conversation.add_system(
        f"Current architecture:\n\n{present_to_llm(list(architecture.values()))}\n\n",
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

        try:
            for json_ in jsons:
                if isinstance(json_, List):
                    for j in json_:
                        jsons.append(j)
                    continue

                if "action" not in json_:
                    raise ValueError(
                        'No action found in the json. Remember to use "add", "update" or "remove".'
                    )
                action = json_["action"]
                key = (
                    json_["namespace"] + "." + json_["name"]
                    if json_["namespace"]
                    else json_["name"]
                )
                if action != Action.REMOVE:
                    component = Component.model_validate(json_)
                    if isinstance(component.root, Infrastructure):
                        conversation.add_system(
                            "You can't add, update or remove infrastructure. "
                            f"Skipping :: {key}."
                        )
                        continue

                else:
                    component = None
                component_to_update = ComponentToUpdate(
                    action=action, key=key, base=component
                )

                if (
                    component_to_update.key in architecture
                    and architecture[component_to_update.key].update_status == "blocked"
                ):
                    raise ValueError(
                        f"Unable to {action} component :: {key} "
                        "because it has been marked as blocked."
                    )
                components_to_update[key] = component_to_update

            for component in components_to_update.values():
                if component.action != Action.REMOVE:
                    for dependency in component.base.root.dependencies:
                        if (
                            dependency not in architecture
                            and dependency not in components_to_update
                        ):
                            raise ValueError(
                                f"Unable to {component.action} component :: {component.key} "
                                f"because its dependency {dependency} is not in the architecture. "
                                "Remember to use namespace.name."
                            )
        except Exception as e:
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
                architecture[component.key].update_status = "to_update"
        config["architecture"] = list(architecture.values())
        save_config(config)
        conversation.persist(app_name, user, name="conversation_architecture")

        return config, conversation
