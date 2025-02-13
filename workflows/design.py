import json
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
    return json.dumps(
        [c.design.model_dump() for c in architecture if c.update_status != "to_remove"],
        indent=4,
    )


PROMPT = f"""You are helpful assistant that designs distributed systems.

The system's architecture is represented as a json in the following format:

[
    {{
        "type": "infrastructure",
        "name": "The name of the infrastructure",
        "config": {{"The details of the infrastructure"}}
    }},
    {{
        "type": "microservice",
        "name": "The name of the microservice",
        "endpoints": [
            {{
                "type": "function",
                # Attributes of the function,
                "is_endpoint": true
            }}
        ]
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
        "dependencies": ["The other namespace.datamodels that the model is associated with."]
    }},
    {{
       "type": "function",
        "name": "The name of the function",
        "namespace": "The virtual location of the code, ie, the file path. Use a dot notation.",
        "purpose": "What the function does. Code will be generated from this description. Mention every important detail.",
        "dependencies": ["The other namespace.functions or namespace.datamodels that the code depends on."],
        "pypi_packages": ["The pypi packages that the code will need, eg, package==version."],
        "is_endpoint": true or false whether this is a FastAPI endpoint
    }}
    ...
]

There are four types of components: infrastructure, microservices, datamodels and functions.

infrastructure represents Google Cloud Platform infrastructure that you have access to.

microservices represent other systems. The endpoints of the microservices are exposed and you can only access them via HTTP requests. You can't have a direct dependency on those endpoints.

datamodels represent sqlalchemy models.

functions represent the business logic. `app.main` and the `app.modassembly` namespace are reserved for internal use. They will be updated for you.

datamodels and functions will be executed on Google Cloud Run as a FastAPI.

Your goal is to interpret the user's requests and add/update/remove datamodels or functions to design the architecture that matches the user's needs. To add or update a datamodel or function, use the following format:

{{
    "action":"update",
    "type": "datamodel" or "function",
    # Attributes of the datamodel or function
}}

To remove a datamodel or function, use the following format:

{{
    "action": "remove",
    "name": "The name of the datamodel or function to remove",
    "namespace": "The namespace of the datamodel or function"
}}

Use the format:
```json
...
```

Follow a microservices design pattern. If the data that you need is exposed by another microservice, avoid creating a new datamodel and duplicating the functionality. Instead, make a call to the relevant microservice.
        
Design an architecture that is easy to refactor and easy to extend. Break apart each feature into steps. Identify the steps that belong as independent functions. (**Important**) functions should have less than 50 lines of code. Composable architectures are easier to maintain.

Add/update/remove components in the following order:

1. Less dependencies
2. More dependencies
...
N. Endpoint

(**Important**) Every time that you update a component, update its upstream and downstream dependencies. To rename or move a component, first remove it and add it again. Be brief."""


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
                    if (
                        key in architecture
                        and architecture[key].update_status == "blocked"
                    ):
                        raise ValueError(
                            f"Unable to {action} component :: {key} "
                            "because it has been marked as blocked."
                        )
                    if action != Action.REMOVE:
                        component = Component.model_validate(json_)
                        if (
                            isinstance(component.root, DataModel)
                            and "External.CloudSQL" not in architecture
                            and "External.CloudSQL" not in components_to_update
                        ):
                            raise ValueError(
                                f"Unable to {action} component :: {key} "
                                "because there is no infrastructure to support it."
                            )
                        """component.dependencies = [
                            (
                                "app." + dependency
                                if not dependency.startswith("External")
                                and not dependency.startswith("app.")
                                else dependency
                            )
                            for dependency in component.dependencies
                        ]"""
                        if isinstance(component.root, Function) or isinstance(
                            component.root, DataModel
                        ):
                            for dependency in component.root.dependencies:
                                if (
                                    dependency not in architecture
                                    and dependency not in components_to_update
                                ):
                                    raise ValueError(
                                        f"Unable to {action} component :: {component.key} "
                                        f"because the `dependency` :: {dependency} doesn't exist in the architecture. "
                                        "Add components in the order of their dependencies. "
                                        "Remember that you can't have a direct dependency on microservices. "
                                        "You must rely on HTTP requests."
                                    )
                        """if isinstance(component.root, Infrastructure):
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
                                    break"""
                        if (
                            isinstance(component.root, Function)
                            or isinstance(component.root, DataModel)
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
                    component = Function.model_validate(json_)
                    if not component.key == "app.main":
                        conversation.add_system(
                            f"Will remove and add :: {component.key}."
                            "\n\nRemember to use update/remove operations."
                        )
                        jsons.append(
                            {
                                "action": Action.REMOVE,
                                "name": component.name,
                                "namespace": component.namespace,
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
