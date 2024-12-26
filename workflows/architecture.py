import argparse
import json
import os
from typing import Any, Dict
from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.io import user_input, print_system
from utils.state import Conversation
from workflows.helpers import (
    RawComponent,
    build_graph,
    extract_json,
    install_requirements,
    visualize_graph,
)


initial_architecture = [
    RawComponent(
        type="function",
        name="main",
        purpose="The main FastAPI script",
        uses=["Other functions or structs"],
        pypi_packages=[
            "fastapi==0.115.6",
            "pydantic==2.10.3",
            "python-dotenv==1.0.1",
            "uvicorn==0.34.0",
        ],
        is_endpoint=False,
    )
]


def run(app_name: str, system_description: str) -> Dict[str, Any]:
    os.makedirs(f"db/repos/{app_name}", exist_ok=True)
    with open(f"db/repos/{app_name}/config.json", "w") as f:
        json.dump({}, f)

    conversation = Conversation()
    conversation.add_system(
        """You are helpful AI assistant that designs backend architectures.

The system that you design will be exposed via a set of FastAPI endpoints. If needed, you can rely on 2 types of external infrastructure: a database and http requests."""
    )
    conversation.add_user(
        f"""Consider the following system: {system_description}.

Design the architecture (no code) of the python module (purely backend) that implements it. Be opinionated and specific in your decisions.
Use a modular and composable design pattern. Prefer functions over classes.
Consider the control flow. For each component, specify the other components that it uses internally."""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    aux_convo = conversation.copy()
    aux_convo.add_user(
        """What types of external infrastructure does this architecture rely on?
        
```json
["database", "http", "other"]
````"""
    )
    aux_message = llm.stream_text(aux_convo)
    external_infrastructure = extract_json(aux_message, pattern=r"```json\n(.*)\n```")

    if "other" in external_infrastructure:
        raise ValueError("This type of infrastructure is not supported yet.")

    conversation.add_user(
        f"""Map the architecture into a json like the following one:

```json
[
    {{
        "type": "struct" or "function",
        "name": "The function or struct name",
        "purpose": "...",
        "uses": ["The other struct or functions that this component uses internally."],
        "pypi_packages": ["The pypi packages that it will need"],
        "is_api": true or false whether this is a FastAPI endpoint
    }},
    ...
]
```

The relationship between each component in the architecture is defined by the "uses" field."""
    )

    if "database" in external_infrastructure:
        initial_architecture.append(
            RawComponent(
                type="function",
                name="get_db",
                purpose="Initializes the database and gets a session.",
                uses=[],
                pypi_packages=["psycopg2-binary==2.9.10", "sqlalchemy==2.0.36"],
                is_endpoint=False,
            )
        )
        conversation.add_user("Add the necessary database models.")

    conversation.add_user(
        f"""
Complete the architecture:

```json
{json.dumps([c.model_dump() for c in initial_architecture], indent=4)}
```
"""
    )

    tries = 0
    while tries < 3:
        assistant_message = llm.stream_text(conversation)
        conversation.add_assistant(assistant_message)

        architecture_raw = extract_json(
            assistant_message, pattern=r"```json\n(.*)\n```"
        )
        architecture = {
            a["name"]: RawComponent.model_validate(a) for a in architecture_raw
        }

        try:
            pypi_packages = set()
            for component in architecture.values():
                if " " in component.name:
                    raise ValueError(f"Invalid component name: {component.name}.")
                for dependency in component.uses:
                    if dependency not in architecture:
                        raise ValueError(
                            f'{dependency} in "uses" of '
                            f"{component.name} is not a component of the architecture"
                        )
                pypi_packages.update(component.pypi_packages)

            install_requirements(pypi_packages, app_name)
            break
        except Exception as e:
            print_system(e)
            tries += 1
            if tries == 2:
                raise e
            conversation.add_user(
                f"Found the following error: {e}. Please fix it and generate the json again."
            )

    # G = build_graph(list(architecture.values()))
    # visualize_graph(G)

    output_architecture = {
        "architecture": [s.model_dump() for s in architecture.values()],
        "external_infrastructure": external_infrastructure,
    }
    with open(f"db/repos/{app_name}/config.json", "w") as f:
        json.dump(output_architecture, f)

    return output_architecture


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()
    system_description = user_input("system description: ")

    run(args.app, system_description)
