import argparse
import json
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.architecture import load_config, save_config
from utils.io import print_system
from utils.state import Conversation
from workflows.helpers import execute_deploy, extract_json
from workflows.subworkflows import write_function


ERROR = """ERROR 2024-12-29T04:06:29.230750Z Traceback (most recent call last): File "/usr/local/lib/python3.13/site-packages/uvicorn/protocols/http/h11_impl.py", line 403, in run_asgi result = await app( # type: ignore[func-returns-value]
DEFAULT 2024-12-29T04:06:29.230752Z ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
DEFAULT 2024-12-29T04:06:29.230755Z self.scope, self.receive, self.send
DEFAULT 2024-12-29T04:06:29.230758Z ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
DEFAULT 2024-12-29T04:06:29.230760Z )
DEFAULT 2024-12-29T04:06:29.230763Z ^
DEFAULT 2024-12-29T04:06:29.230766Z File "/usr/local/lib/python3.13/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
DEFAULT 2024-12-29T04:06:29.230770Z return await self.app(scope, receive, send)
DEFAULT 2024-12-29T04:06:29.230772Z ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
DEFAULT 2024-12-29T04:06:29.230775Z File "/usr/local/lib/python3.13/site-packages/fastapi/applications.py", line 1054, in __call__
DEFAULT 2024-12-29T04:06:29.230778Z await super().__call__(scope, receive, send)
DEFAULT 2024-12-29T04:06:29.230780Z File "/usr/local/lib/python3.13/site-packages/starlette/applications.py", line 113, in __call__
DEFAULT 2024-12-29T04:06:29.230783Z await self.middleware_stack(scope, receive, send)
DEFAULT 2024-12-29T04:06:29.230785Z File "/usr/local/lib/python3.13/site-packages/starlette/middleware/errors.py", line 187, in __call__
DEFAULT 2024-12-29T04:06:29.230788Z raise exc
DEFAULT 2024-12-29T04:06:29.230790Z File "/usr/local/lib/python3.13/site-packages/starlette/middleware/errors.py", line 165, in __call__
DEFAULT 2024-12-29T04:06:29.230793Z await self.app(scope, receive, _send)
DEFAULT 2024-12-29T04:06:29.230795Z File "/usr/local/lib/python3.13/site-packages/starlette/middleware/cors.py", line 85, in __call__
DEFAULT 2024-12-29T04:06:29.230798Z await self.app(scope, receive, send)
DEFAULT 2024-12-29T04:06:29.230801Z File "/usr/local/lib/python3.13/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
DEFAULT 2024-12-29T04:06:29.230804Z await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
DEFAULT 2024-12-29T04:06:29.230807Z File "/usr/local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
DEFAULT 2024-12-29T04:06:29.230809Z raise exc
DEFAULT 2024-12-29T04:06:29.230811Z File "/usr/local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
DEFAULT 2024-12-29T04:06:29.230814Z await app(scope, receive, sender)
DEFAULT 2024-12-29T04:06:29.230816Z File "/usr/local/lib/python3.13/site-packages/starlette/routing.py", line 715, in __call__
DEFAULT 2024-12-29T04:06:29.230819Z await self.middleware_stack(scope, receive, send)
DEFAULT 2024-12-29T04:06:29.230822Z File "/usr/local/lib/python3.13/site-packages/starlette/routing.py", line 735, in app
DEFAULT 2024-12-29T04:06:29.230824Z await route.handle(scope, receive, send)
DEFAULT 2024-12-29T04:06:29.230827Z File "/usr/local/lib/python3.13/site-packages/starlette/routing.py", line 288, in handle
DEFAULT 2024-12-29T04:06:29.230829Z await self.app(scope, receive, send)
DEFAULT 2024-12-29T04:06:29.230832Z File "/usr/local/lib/python3.13/site-packages/starlette/routing.py", line 76, in app
DEFAULT 2024-12-29T04:06:29.230835Z await wrap_app_handling_exceptions(app, request)(scope, receive, send)
DEFAULT 2024-12-29T04:06:29.230837Z File "/usr/local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
DEFAULT 2024-12-29T04:06:29.230841Z raise exc
DEFAULT 2024-12-29T04:06:29.230844Z File "/usr/local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
DEFAULT 2024-12-29T04:06:29.230847Z await app(scope, receive, sender)
DEFAULT 2024-12-29T04:06:29.230849Z File "/usr/local/lib/python3.13/site-packages/starlette/routing.py", line 73, in app
DEFAULT 2024-12-29T04:06:29.230852Z response = await f(request)
DEFAULT 2024-12-29T04:06:29.230854Z ^^^^^^^^^^^^^^^^
DEFAULT 2024-12-29T04:06:29.230857Z File "/usr/local/lib/python3.13/site-packages/fastapi/routing.py", line 327, in app
DEFAULT 2024-12-29T04:06:29.230859Z content = await serialize_response(
DEFAULT 2024-12-29T04:06:29.230862Z ^^^^^^^^^^^^^^^^^^^^^^^^^
DEFAULT 2024-12-29T04:06:29.230864Z ...<9 lines>...
DEFAULT 2024-12-29T04:06:29.230866Z )
DEFAULT 2024-12-29T04:06:29.230868Z ^
DEFAULT 2024-12-29T04:06:29.230870Z File "/usr/local/lib/python3.13/site-packages/fastapi/routing.py", line 176, in serialize_response
DEFAULT 2024-12-29T04:06:29.230876Z raise ResponseValidationError(
DEFAULT 2024-12-29T04:06:29.230879Z errors=_normalize_errors(errors), body=response_content
DEFAULT 2024-12-29T04:06:29.230881Z )
DEFAULT 2024-12-29T04:06:29.230890Z fastapi.exceptions.ResponseValidationError: 1 validation errors:
DEFAULT 2024-12-29T04:06:29.230892Z {'type': 'string_type', 'loc': ('response', 0, 'order_date'), 'msg': 'Input should be a valid string', 'input': datetime.datetime(2024, 12, 29, 4, 6, 17, 346000)}"""


def run(app_name: str, config: Dict[str, Any]):
    architecture = {c.base.key: c for c in config["architecture"]}

    conversation = Conversation()
    conversation.add_system(
        """You are a helpful AI assistant that fixes bugs.

Given the log of an error:
1. Identify the set of files that need to be updated to fix it. Ignore tests.
2. Make the minimum set of changes to fix it."""
    )

    conversation.add_user(
        f"Consider the following python architecture: {json.dumps([c.model_dump() for c in config['architecture']], indent=2)}"
    )
    conversation.add_user(f"Consider the following error:\n\n{ERROR}")
    conversation.add_user("What is the plan to fix this error?")
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    conversation.add_user(
        """What are the components that need to be updated? Use the following format:

```json
["namespace.name", "namespace.name", ...]
```"""
    )
    assistant_message = llm.stream_text(conversation)
    conversation.add_assistant(assistant_message)

    components = extract_json(assistant_message, pattern=r"```json\n(.*)\n```")[0]
    for component in components:
        component_to_fix = architecture[component]
        conversation.add_user(f"Fix :: {component}")
        output = write_function(app_name, component_to_fix, conversation.copy())

        conversation.add_assistant(output.assistant_message)
        assert output.component.file
        conversation.add_user(f"I saved the code in {output.component.file.path}.")
        architecture[output.component.base.key].file = output.component.file

        config["architecture"] = list(architecture.values())
        save_config(config)

    print_system("Deploying application...")
    service_url = execute_deploy(app_name)
    print_system(f"{service_url}/docs")
    return f"{service_url}/docs"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    config = load_config(args.app)

    run(args.app, config)
