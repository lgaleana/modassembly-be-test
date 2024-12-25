import json
import os
import argparse
import subprocess
from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.io import user_input, print_system
from utils.state import Conversation
from workflows.helpers import RawComponent, build_graph, extract_json, visualize_graph


initial_architecture = [
    RawComponent(
        type="function",
        name="main",
        purpose="The main FastAPI function",
        uses=["Fill it in"],
        pypi_packages=[
            "fastapi[standard]==0.115.6",
            "pydantic==2.10.3",
            "python-dotenv==1.0.1",
        ],
        is_endpoint=False,
    )
]


def run(app_name: str, user_story: str) -> None:
    conversation = Conversation()
    conversation.add_system(
        """You are helpful AI assistant that designs backend architectures.

The system that you design will be exposed via a set of FastAPI endpoints. You can rely on 3 types of external infrastructure (not mandatory): a database, the file system and http requests."""
    )
    conversation.add_user(
        f"""Consider the following user story: {user_story}.

Design the architecture (no code) of the python module (purely backend) that implements it. Be opinionated and specific in your decisions.
Use a modular and composable design pattern. Prefer functions over classes.
Consider the control flow. For each component, specify the other components that it uses internally."""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    conversation.add_user(
        """What types of external infrastructure does this architecture rely on?
        
```json
["database", "file_system", "http", "other"]
````"""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    external_infrastructure = extract_json(
        assistant_message, pattern=r"```json\n(.*)\n```"
    )
    if "database" in external_infrastructure:
        initial_architecture.append(
            RawComponent(
                type="function",
                name="get_db",
                purpose="Context manager for getting a database session",
                uses=[],
                pypi_packages=["sqlmodel==0.0.22"],
                is_endpoint=False,
            )
        )
        conversation.add_user("Remember to add your database models.")
    if "other" in external_infrastructure:
        raise ValueError("This type of infrastructure is not supported yet.")

    conversation.add_user(
        f"""Map the architecture into the following json:

```json
[
    {{
        "type": "struct" or "function",
        "name": "The function or struct name",
        "purpose": "...",
        "uses": ["The other struct or functions that this component uses internally."],
        "pypi_packages": ["The pypi packages that it will need"],
        "is_api": true or false whether this is an endpoint to the application
    }},
    ...
]
```  

Complete the architecture:

```json
{json.dumps([c.model_dump() for c in initial_architecture], indent=4)}
```
"""
    )

    tries = 0
    while tries < 2:
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
                pypi_packages.update(component.pypi_packages)

            print_system("Installing requirements...")
            venv_python = f"venv/bin/python3"
            subprocess.run(
                [
                    venv_python,
                    "-m",
                    "pip",
                    "install",
                    *pypi_packages,
                ],
                check=True,
            )
            break
        except Exception as e:
            print_system(e)
            conversation.add_user(
                f"Found the following error: {e}. Please fix it and generate the json again."
            )
            tries += 1

    G = build_graph(list(architecture.values()))
    visualize_graph(G)

    os.makedirs(f"db/repos/{app_name}", exist_ok=True)
    with open(f"db/repos/{app_name}/config.json", "w") as f:
        json.dump(
            {
                "architecture": [s.model_dump() for s in architecture.values()],
                "external_infrastructure": external_infrastructure,
            },
            f,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()
    user_story = user_input("user story: ")

    run(args.app, user_story)
