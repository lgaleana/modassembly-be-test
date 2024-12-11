from dotenv import load_dotenv

load_dotenv()

from ai import llm
from ai.llm_class import llmc
from helpers import extract_json, build_graph
from state import Conversation


if __name__ == "__main__":
    conversation = Conversation()
    conversation.add_user(
        """Design the architecture (no code) of a python module that scrapes the text of any website. Use a modular and composable design pattern. Prefer functions over classes. For each component, specify the other components that it calls internally."""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    conversation.add_user(
        """Express the control flow using a json format. Each component must be called by another component. For example:

``json
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

    conversation.add_user(
        """Declare the list of packages that will need to be installed, if any. Use the following json format

```json
["package1", "package2", ...]
```"""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    pypi_packages = extract_json(assistant_message, pattern=r"```json\n(.*?)```")
