from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from ai import llm
from workflows.helpers import extract_from_pattern
from utils.state import Conversation
from utils.static_analysis import check_imports


def get_architecture(conversation: Conversation, user_story: str) -> Conversation:
    conversation.add_user(
        f"""Consider the following user story: {user_story}.

Design the architecture (no code) of the python module (purely backend) that implements it. Be opinionated in your decisions.
Use a modular and composable design pattern. Prefer functions over classes.
Consider the control flow. For each component, specify the other components that it calls internally."""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)
    return conversation


class LevelContext(BaseModel):
    component: str
    user_message: str
    assistant_message: str
    code: str


def write_function(
    component: str, conversation: Conversation, *, tries: int = 2
) -> LevelContext:
    def _write_function(try_: int) -> LevelContext:
        user_message = f"""Write the code for: {component}. Use the following format:
```python
...
```"""
        conversation.add_user(user_message)
        assistant_message = llm.stream_text(conversation)

        code = extract_from_pattern(assistant_message, pattern=r"```python\n(.*?)```")
        try:
            check_imports(code)
            return LevelContext(
                component=component,
                user_message=user_message,
                assistant_message=assistant_message,
                code=code,
            )
        except Exception as e:
            if try_ == tries:
                raise e
            conversation.add_user(f"I found the following error:\n\n{e}.")
            return _write_function(try_ + 1)

    return _write_function(0)
