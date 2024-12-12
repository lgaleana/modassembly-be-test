import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from ai.llm_class import llmc
from utils.state import Conversation
from utils.io import user_input
from workflows.helpers import (
    build_graph,
    extract_json,
    group_nodes_by_dependencies,
)
from workflows.subworkflows import write_function


if __name__ == "__main__":
    user_story = user_input("user story: ")

    conversation = Conversation()
    conversation.add_user(
        f"""Consider the following user story: {user_story}.

Design the architecture (no code) of the python module that implements it. Use a modular and composable design pattern. Prefer functions over classes. For each component, specify the other components that it calls internally."""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    conversation.add_user(
        """Express the control flow using a json format. For example:

```json
{
  "function1": {
    "calls": []
  },
  "function2": {
    "calls": ["function1]
  },
  "function3": {
    "calls": ["function2"]
  }
}
```"""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    architecture = extract_json(assistant_message, pattern=r"```json\n(.*?)```")
    build_graph(architecture)

    # conversation.add_user(
    #     """Declare the list of packages that will need to be installed, if any. Use the following json format

    # ```json
    # ["package1", "package2", ...]
    # ```"""
    # )
    # assistant_message = llm.stream_text(conversation)
    # conversation.add_assistant(assistant_message)

    # pypi_packages = extract_json(assistant_message, pattern=r"```json\n(.*?)```")

    nodes_to_parallelize = group_nodes_by_dependencies(architecture)
    for level in nodes_to_parallelize:
        with ThreadPoolExecutor(max_workers=10) as executor:
            outputs = list(
                executor.map(write_function, level, [conversation.copy()] * len(level))
            )
        for output in outputs:
            conversation.add_user(output.user_message)
            conversation.add_assistant(output.assistant_message)

            file_path = f"repo/functions/{output.component}.py"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            conversation.add_user(f"I saved the code in {file_path}.")
            with open(file_path, "w") as f:
                f.write(output.code)
