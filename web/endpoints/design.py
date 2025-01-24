from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json

from ai import llm
from app.logging.get_user_activity_logs import get_user_activity_logs
from app.models.User import User
from utils.config.architecture import ImplementedComponent, load_config
from utils.state import Conversation
from web.modassembly_web.app.modassembly.authentication.authenticate import authenticate
from workflows import brainstorm
from workflows import design
from workflows.helpers import extract_json


CHAT_LIMIT = 50
MAP_LIMIT = 50


router = APIRouter()


class Request(BaseModel):
    app_name: str
    user_message: str
    architecture: List[ImplementedComponent] = []


@router.post("/chat")
def chat(request: Request, user: User = Depends(authenticate)) -> StreamingResponse:
    logs = get_user_activity_logs(user.username, "brainstorm")
    if len(logs) > CHAT_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Usage limit exceeded.",
        )

    def generate():
        for chunk in brainstorm.run(
            request.app_name, request.user_message, str(user.username)
        ):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


class MapResponse(BaseModel):
    config: Dict[str, Any]
    conversation: List[Dict[str, Any]]


@router.post("/map", response_model=MapResponse)
def map(request: Request, user: User = Depends(authenticate)) -> MapResponse:
    logs = get_user_activity_logs(user.username, "design")
    if len(logs) > MAP_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Usage limit exceeded.",
        )
    config, conversation = design.run(
        request.app_name,
        str(user.username),
        request.user_message,
    )
    return MapResponse(config=config, conversation=conversation)


def get_brainstorm_context(
    brainstorm_conversation: Conversation,
    architecture_conversation: Conversation,
    message_type: str,
) -> str:
    last_brainstorm_message = None
    for message in reversed(architecture_conversation):
        if "type" in message and message["type"] == message_type:
            last_brainstorm_message = message
            break

    architecture_context_start = 1
    if last_brainstorm_message is not None:
        for i, message in reversed(list(enumerate(brainstorm_conversation))):
            if message["content"] in last_brainstorm_message["content"]:
                architecture_context_start = i + 1
                break

    context = ""
    for message in brainstorm_conversation[architecture_context_start:]:
        if message["role"] != "system":
            context += message["role"] + ": " + message["content"] + "\n\n"
    return context


@router.post("/sync")
def sync(request: Request, user: User = Depends(authenticate)) -> None:
    logs = get_user_activity_logs(user.username, "brainstorm")
    if len(logs) > MAP_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Usage limit exceeded.",
        )

    conversation = Conversation.load(
        app_name=request.app_name,
        user=str(user.username),
        name="conversation_brainstorm",
    )
    config = load_config(request.app_name, str(user.username))

    conversation.add_user(
        """Let's update the architecture with the latest changes. Think in terms of components. Think in terms of infrastructure, data models and functions.

In one sentence, tell me a summary of the changes that we're trying to make since it was last updated.
Then, in one sentence, tell me all the infrastructure to add, update or remove (if any): "For now, ..."."""
    )
    user_message = llm.stream_text(conversation)
    conversation.add_assistant(user_message)
    design.run(
        request.app_name,
        str(user.username),
        user_message,
    )

    conversation.add_user(
        "In one sentence, tell me all the data models to add, update or remove (if any)."
    )
    user_message = llm.stream_text(conversation)
    conversation.add_assistant(user_message)
    design.run(
        request.app_name,
        str(user.username),
        f"{user_message} (add infrastructure first, if not present)",
    )

    conversation.add_user(
        """Now, consider how the entire logic of the architecture is changing. Refactoring an architecture is not easy. So we'll do it in steps. Be very careful.
        
First, we're going to remove all functions that are no longer needed. Then, we're going to add/update all the new functionality.

It's very useful to think in terms of flows that start with an http request and end with an http response. Use the following format:

(NOTE: app.main and the app.modassembly namespace are reserved for internal use. They can't be updated.)
```json
{
    "remove": "In one sentence, tell me all the functions to remove" or null,
    "add": [
        "Add/update an/the endpoint that does X, Y...",
        ...
    ] or []
}
```"""
    )
    user_message = llm.stream_text(conversation)
    refactor = extract_json(user_message)[0]
    if refactor["remove"]:
        design.run(
            request.app_name,
            str(user.username),
            refactor["remove"],
        )
    if refactor["add"]:
        for flow in refactor["add"]:
            design.run(
                request.app_name,
                str(user.username),
                flow,
            )

    design.run(
        request.app_name,
        str(user.username),
        "Consider each E2E flow.Remove the duplicated logic.",
    )

    conversation = Conversation.load(
        app_name=request.app_name,
        user=str(user.username),
        name="conversation_brainstorm",
    )
    conversation.add_system(
        f"Current architecture:\n\n{brainstorm.present_to_llm(config['architecture'])}",
        type_="architecture",
    )
    conversation.persist(
        request.app_name, str(user.username), name="conversation_brainstorm"
    )
