import json
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()

from utils.files import File
from utils.state import Conversation
from workflows.helpers import (
    Component,
    REPOS,
    build_graph,
    group_nodes_by_dependencies,
    load_helpers,
    save_files,
    visualize_graph,
)
from workflows.subworkflows import write_function


if __name__ == "__main__":
    with open("db/repos/example/config.json", "r") as f:
        config = json.load(f)
    architecture = {
        a["name"]: Component.model_validate(a) for a in config["architecture"]
    }
    os.mkdir(f"db/repos/{config['name']}/app")

    G = build_graph(list(architecture.values()))
    visualize_graph(G)

    conversation = Conversation()
    conversation.add_user(
        f"Consider the following architecture of a python architecture: {architecture}"
    )

    db_helper, main = load_helpers(architecture)
    for helper in [db_helper, main]:
        conversation.add_user(
            f"I wrote the code for:\n\n```python\n{helper.content}\n```"
        )
        conversation.add_user(f"I saved the code in {helper.path}.")

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

            file_path = f"app/components/{output.component}.py"
            os.makedirs(
                os.path.dirname(f"{REPOS}/{config['name']}/{file_path}"), exist_ok=True
            )
            conversation.add_user(f"I saved the code in {file_path}.")
            with open(f"{REPOS}/{config['name']}/{file_path}", "w") as f:
                f.write(output.code)
            architecture[output.component].file = File(
                path=file_path, content=output.code
            )

    save_files(config["name"], db_helper, main, architecture)
