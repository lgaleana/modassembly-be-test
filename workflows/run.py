import json
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from ai.llm_class import llmc
from utils.files import File
from utils.state import Conversation
from utils.static_analysis import extract_router_name
from workflows.helpers import (
    Component,
    build_graph,
    group_nodes_by_dependencies,
    visualize_graph,
)
from workflows.subworkflows import write_function


if __name__ == "__main__":
    with open("db/architectures/inventory.json", "r") as f:
        architecture = {a["name"]: Component.model_validate(a) for a in json.load(f)}

    G = build_graph(list(architecture.values()))
    visualize_graph(G)

    has_db = False
    for component in architecture.values():
        for external in component.external_infrastructure:
            if external == "database":
                has_db = True

    conversation = Conversation()
    conversation.add_user(
        f"Consider the following architecture of a python architecture: {architecture}"
    )

    if has_db:
        db_helper_path = "repo/helpers/db.py"
        with open(db_helper_path, "r") as f:
            conversation.add_user(
                f"I wrote the code for:\n\n```python\n{f.read()}\n```"
            )
            conversation.add_user(f"I saved the code in {db_helper_path}.")
    main_path = "repo/main.py"
    with open("repo/_templates/main.py", "r") as f:
        main_content = f.read()
        conversation.add_user(
            f"I wrote the code for:\n\n```python\n{main_content}\n```"
        )
        conversation.add_user(f"I saved the code in {main_path}.")

    nodes_to_parallelize = group_nodes_by_dependencies(list(architecture.values()))
    for level in nodes_to_parallelize:
        with ThreadPoolExecutor(max_workers=10) as executor:
            outputs = list(
                executor.map(
                    write_function, level, [conversation.copy() for _ in level]
                )
            )
        for output in outputs:
            conversation.add_user(output.user_message)
            conversation.add_assistant(output.assistant_message)

            file_path = f"repo/components/{output.component}.py"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            conversation.add_user(f"I saved the code in {file_path}.")
            with open(file_path, "w") as f:
                f.write(output.code)
            architecture[output.component].file = File(
                path=file_path, content=output.code
            )

    with open(main_path, "w") as f:
        main_content += "\n"
        for component in architecture.values():
            if component.is_api:
                assert component.file
                module = component.file.path.replace(".py", "").replace("/", ".")
                router_name = extract_router_name(component.file)
                main_content += f"from {module} import {router_name}\n"
                main_content += f"app.include_router({router_name})\n"
        f.write(main_content)
