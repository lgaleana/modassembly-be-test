import ast

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from ai import llm
from ai.llm_class import llmc
from workflows.helpers import extract_from_pattern
from utils.state import Conversation


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
