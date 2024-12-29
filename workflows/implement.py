import json
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import List

from dotenv import load_dotenv

load_dotenv()

from utils.architecture import (
    Function,
    SQLAlchemyModel,
    load_config,
    save_config,
)
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import (
    REPOS,
    execute_deploy,
    group_nodes_by_dependencies,
    update_main,
)
from workflows.subworkflows import save_files, write_function


def run(app_name: str) -> str:
    config = load_config(app_name)
    assert isinstance(config["architecture"], List)
    architecture = {c.base.key: c for c in config["architecture"]}
    raw_architecture = [c.base.model_dump() for c in architecture.values()]
    external_infrastructure = ["database", "http"]

    conversation = Conversation()
    conversation.add_user(
        f"Consider the following python architecture: {json.dumps(raw_architecture, indent=2)}"
    )

    save_files(app_name, architecture, external_infrastructure, conversation)

    architecture.pop("main")
    architecture.pop("helpers.get_db")
    sys.path.append(f"{REPOS}/{app_name}")
    models_to_parallelize = group_nodes_by_dependencies(
        [m for m in architecture.values() if isinstance(m.base.root, SQLAlchemyModel)]
    )
    functions_to_parallelize = group_nodes_by_dependencies(
        [f for f in architecture.values() if isinstance(f.base.root, Function)]
    )
    for level in models_to_parallelize + functions_to_parallelize:
        print_system(f"Implementing :: {level}\n")
        with ThreadPoolExecutor(max_workers=10) as executor:
            outputs = list(
                executor.map(
                    write_function,
                    [app_name] * len(level),
                    [architecture[l] for l in level],
                    [conversation.copy() for _ in level],
                )
            )
        for output in outputs:
            assert output.component.file
            conversation.add_user(output.user_message)
            conversation.add_assistant(output.assistant_message)
            conversation.add_user(f"I saved the code in {output.component.file.path}.")
            architecture[output.component.base.key].file = output.component.file

    update_main(app_name, architecture, external_infrastructure)

    print_system("Deploying application...")
    service_url = execute_deploy(app_name)

    save_config(config)
    print_system(f"{service_url}/docs")
    return f"{service_url}/docs"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    run(args.app)
