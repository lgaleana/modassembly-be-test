import json
import argparse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

from utils.architecture import (
    Function,
    ImplementedComponent,
    SQLAlchemyModel,
    load_config,
    save_config,
    update_architecture_diff,
)
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import (
    execute_deploy,
    group_nodes_by_dependencies,
    update_main,
)
from workflows.subworkflows import ImplementationContext, save_files, write_component


def run(config: Dict[str, Any], new_architecture: List[ImplementedComponent]) -> str:
    app_name = config["name"]
    saved_architecture = config["architecture"]
    external_infrastructure = ["database", "http"]

    architecture = {}
    for component in saved_architecture:
        if not component.file:
            print_system(f"Will update {component.base.key}")
            architecture[component.base.key] = component
    for new_component in new_architecture:
        for old_component in saved_architecture:
            if (
                new_component.base.key == old_component.base.key
                and new_component != old_component
            ):
                print_system(f"Will update {new_component.base.key}")
                architecture[new_component.base.key] = new_component
                break

    conversation = Conversation()
    raw_architecture = [c.base.model_dump() for c in architecture.values()]
    conversation.add_user(
        f"Consider the following python architecture: {json.dumps(raw_architecture, indent=2)}"
    )

    save_files(app_name, architecture, external_infrastructure, conversation)

    architecture.pop("main")
    architecture.pop("helpers.get_db")
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
                    write_component,
                    [app_name] * len(level),
                    [ImplementationContext(component=architecture[l]) for l in level],
                    [conversation.copy() for _ in level],
                )
            )

        def _update(context: ImplementationContext) -> None:
            assert (
                context.user_message
                and context.assistant_message
                and context.component.file
            )
            conversation.add_user(context.user_message)
            conversation.add_assistant(context.assistant_message)
            conversation.add_user(f"I saved the code in {context.component.file.path}.")
            architecture[context.component.base.key].file = context.component.file

        correct_implementations = [o for o in outputs if not o.error]
        wrong_implementations = [o for o in outputs if o.error]
        for output in correct_implementations:
            _update(output)

        if not wrong_implementations:
            continue

        for output in wrong_implementations:
            while True:
                if output.tries == 3:
                    assert output.error
                    raise output.error
                assert output.user_message and output.assistant_message
                conversation.add_user(output.user_message)
                conversation.add_assistant(output.assistant_message)
                conversation.add_user(
                    f"Found errors ::\n\n{output.error}\n\nPlease fix them."
                )
                output = write_component(app_name, output, conversation.copy())
                if not output.error:
                    _update(output)
                    break

    update_architecture_diff(config, list(architecture.values()))
    config = load_config(app_name)

    update_main(app_name, config["architecture"], external_infrastructure)

    print_system("Deploying application...")
    service_url = execute_deploy(app_name)

    save_config(config)
    print_system(f"{service_url}/docs")
    return f"{service_url}/docs"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    config = load_config(args.app)

    run(config, [])
