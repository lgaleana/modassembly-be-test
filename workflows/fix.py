import argparse
import json
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

from ai import llm
from utils.architecture import ImplementedComponent, load_config
from utils.state import Conversation
from workflows.helpers import REPOS


ERROR = """ERROR 2024-12-29T01:31:29.502681Z Traceback (most recent call last): File "/usr/local/lib/python3.13/site-packages/uvicorn/protocols/http/h11_impl.py", line 403, in run_asgi result = await app( # type: ignore[func-returns-value]
DEFAULT 2024-12-29T01:31:29.502685Z ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
DEFAULT 2024-12-29T01:31:29.502690Z self.scope, self.receive, self.send
DEFAULT 2024-12-29T01:31:29.502694Z ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
DEFAULT 2024-12-29T01:31:29.502698Z )
DEFAULT 2024-12-29T01:31:29.502702Z ^
DEFAULT 2024-12-29T01:31:29.502706Z File "/usr/local/lib/python3.13/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
DEFAULT 2024-12-29T01:31:29.502710Z return await self.app(scope, receive, send)
DEFAULT 2024-12-29T01:31:29.502714Z ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
DEFAULT 2024-12-29T01:31:29.502718Z File "/usr/local/lib/python3.13/site-packages/fastapi/applications.py", line 1054, in __call__
DEFAULT 2024-12-29T01:31:29.502722Z await super().__call__(scope, receive, send)
DEFAULT 2024-12-29T01:31:29.502726Z File "/usr/local/lib/python3.13/site-packages/starlette/applications.py", line 113, in __call__
DEFAULT 2024-12-29T01:31:29.502730Z await self.middleware_stack(scope, receive, send)
DEFAULT 2024-12-29T01:31:29.502735Z File "/usr/local/lib/python3.13/site-packages/starlette/middleware/errors.py", line 187, in __call__
DEFAULT 2024-12-29T01:31:29.502738Z raise exc
DEFAULT 2024-12-29T01:31:29.502742Z File "/usr/local/lib/python3.13/site-packages/starlette/middleware/errors.py", line 165, in __call__
DEFAULT 2024-12-29T01:31:29.502747Z await self.app(scope, receive, _send)
DEFAULT 2024-12-29T01:31:29.502751Z File "/usr/local/lib/python3.13/site-packages/starlette/middleware/cors.py", line 85, in __call__
DEFAULT 2024-12-29T01:31:29.502754Z await self.app(scope, receive, send)
DEFAULT 2024-12-29T01:31:29.502758Z File "/usr/local/lib/python3.13/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
DEFAULT 2024-12-29T01:31:29.502762Z await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
DEFAULT 2024-12-29T01:31:29.502766Z File "/usr/local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
DEFAULT 2024-12-29T01:31:29.502770Z raise exc
DEFAULT 2024-12-29T01:31:29.502774Z File "/usr/local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
DEFAULT 2024-12-29T01:31:29.502779Z await app(scope, receive, sender)
DEFAULT 2024-12-29T01:31:29.502784Z File "/usr/local/lib/python3.13/site-packages/starlette/routing.py", line 715, in __call__
DEFAULT 2024-12-29T01:31:29.502787Z await self.middleware_stack(scope, receive, send)
DEFAULT 2024-12-29T01:31:29.502792Z File "/usr/local/lib/python3.13/site-packages/starlette/routing.py", line 735, in app
DEFAULT 2024-12-29T01:31:29.502800Z await route.handle(scope, receive, send)
DEFAULT 2024-12-29T01:31:29.502804Z File "/usr/local/lib/python3.13/site-packages/starlette/routing.py", line 288, in handle
DEFAULT 2024-12-29T01:31:29.502808Z await self.app(scope, receive, send)
DEFAULT 2024-12-29T01:31:29.502812Z File "/usr/local/lib/python3.13/site-packages/starlette/routing.py", line 76, in app
DEFAULT 2024-12-29T01:31:29.502822Z await wrap_app_handling_exceptions(app, request)(scope, receive, send)
DEFAULT 2024-12-29T01:31:29.502827Z File "/usr/local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
DEFAULT 2024-12-29T01:31:29.502830Z raise exc
DEFAULT 2024-12-29T01:31:29.502835Z File "/usr/local/lib/python3.13/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
DEFAULT 2024-12-29T01:31:29.502838Z await app(scope, receive, sender)
DEFAULT 2024-12-29T01:31:29.502843Z File "/usr/local/lib/python3.13/site-packages/starlette/routing.py", line 73, in app
DEFAULT 2024-12-29T01:31:29.502847Z response = await f(request)
DEFAULT 2024-12-29T01:31:29.502851Z ^^^^^^^^^^^^^^^^
DEFAULT 2024-12-29T01:31:29.502855Z File "/usr/local/lib/python3.13/site-packages/fastapi/routing.py", line 327, in app
DEFAULT 2024-12-29T01:31:29.502858Z content = await serialize_response(
DEFAULT 2024-12-29T01:31:29.502863Z ^^^^^^^^^^^^^^^^^^^^^^^^^
DEFAULT 2024-12-29T01:31:29.502866Z ...<9 lines>...
DEFAULT 2024-12-29T01:31:29.502870Z )
DEFAULT 2024-12-29T01:31:29.502874Z ^
DEFAULT 2024-12-29T01:31:29.502878Z File "/usr/local/lib/python3.13/site-packages/fastapi/routing.py", line 176, in serialize_response
DEFAULT 2024-12-29T01:31:29.502891Z raise ResponseValidationError(
DEFAULT 2024-12-29T01:31:29.502895Z errors=_normalize_errors(errors), body=response_content
DEFAULT 2024-12-29T01:31:29.502898Z )
DEFAULT 2024-12-29T01:31:29.502936Z fastapi.exceptions.ResponseValidationError: 1 validation errors:
DEFAULT 2024-12-29T01:31:29.502938Z {'type': 'string_type', 'loc': ('response', 'order_date'), 'msg': 'Input should be a valid string', 'input': datetime.datetime(2024, 12, 29, 1, 31, 3, 378000)}"""


def run(app_name: str, config: Dict[str, Any]):
    conversation = Conversation()
    conversation.add_system("""You're a helpful AI assistant that fixes bugs.""")
    conversation.add_user(
        f"Consider the following python architecture: {json.dumps([c.model_dump() for c in config['architecture']], indent=2)}"
    )
    conversation.add_user(f"Consider the following error: {ERROR}")
    conversation.add_user("What is the plan to fix this error?")
    llm.stream_text(conversation)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app")
    args = parser.parse_args()

    config = load_config(args.app)

    run(args.app, config)
