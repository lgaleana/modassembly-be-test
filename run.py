import ast
import os
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from ai import llm
from ai.llm_class import llmc
from helpers import (
    build_graph,
    extract_from_pattern,
    extract_json,
    group_nodes_by_dependencies,
)
from state import Conversation
from utils.io import user_input


class LevelContext(BaseModel):
    component: str
    user_message: str
    assistant_message: str
    code: str


def write_function(component: str, convo: Conversation) -> LevelContext:
    user_message = f"""Write the code for: {component}. This code will be composed with the rest of the architecture, so make sure that it runs as expected. Use absolute imports. Use the following format:
```python
...
```
"""
    convo.add_user(user_message)
    assistant_message = llm.stream_text(convo)

    code = extract_from_pattern(assistant_message, pattern=r"```python\n(.*?)```")
    ast.parse(code)
    return LevelContext(
        component=component,
        user_message=user_message,
        assistant_message=assistant_message,
        code=code,
    )


if __name__ == "__main__":
    module_to_build = user_input("python module to build: ")

    conversation = Conversation()
    conversation.add_user(
        f"""Design the architecture (no code) of the following python module: {module_to_build}. Use a modular and composable design pattern. Prefer functions over classes. For each component, specify the other components that it calls internally."""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    conversation.add_user(
        """Express the control flow using a json format. Each component must be called by another component and there must be one component that orchestrates the flow. For example:

```json
{
  "function1": {
    "calls": []
    "orchestrates": false
  },
  "function2": {
    "calls": ["function1]
    "orchestrates": false
  },
  "function3": {
    "calls": ["function2"]
    "orchestrates": true
  }
}
```"""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    architecture = extract_json(assistant_message, pattern=r"```json\n(.*?)```")
    build_graph(architecture)

    conversation.add_user(
        """Declare the list of packages that will need to be installed, if any. Use the following json format

```json
["package1", "package2", ...]
```"""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    pypi_packages = extract_json(assistant_message, pattern=r"```json\n(.*?)```")

    nodes_to_parallelize = group_nodes_by_dependencies(architecture)
    for level in nodes_to_parallelize:
        with ThreadPoolExecutor(max_workers=4) as executor:
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
