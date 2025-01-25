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
    conversation.add_user(
        """Consider all the proposed changes since we last updated the architecture. Then let's update the architecture. Refactoring a production system is very risky. So we'll do it step by step. Be very careful.

First, tell me a summary of the changes that we're trying to make.
Then, in one sentence, tell me all the infrastructure to add, update or remove (if any).
In one sentence, tell me all the data models to add, update or remove (if any).

To finish, we'll update the functions:
    In one sentence, tell me all the functions to remove (if any).
    Then think of all the flows that start with an http request and end with an http response.
        Break them apart into steps X, Y, Z...
        Add/update each one of the flows as needed.

Use the following format:
```json
{
    "summary": "...",
    "infrastructure": "For now, add/update/remove..." or null,
    "data_models": "Add/update/remove..." or null,
    "functions": {
        "remove": "Remove..." or null,
        "add": [
            "Add/update an/the endpoint that does X, Y...",
            ...
        ] or []
    }
}
```"""
    )

    refactor = extract_json(llm.stream_text(conversation))[0]
    prefix_message = refactor["summary"] + "\n\n"
    if refactor["infrastructure"]:
        design.run(
            request.app_name,
            str(user.username),
            prefix_message + refactor["infrastructure"],
        )
        prefix_message = ""
    if refactor["data_models"]:
        design.run(
            request.app_name,
            str(user.username),
            prefix_message + refactor["data_models"],
        )
    if refactor["functions"]["remove"]:
        design.run(
            request.app_name,
            str(user.username),
            prefix_message + refactor["functions"]["remove"],
        )
    if refactor["functions"]["add"]:
        for flow in refactor["functions"]["add"]:
            design.run(
                request.app_name,
                str(user.username),
                prefix_message + flow,
            )
            prefix_message = ""

    config = load_config(request.app_name, str(user.username))
    conversation = Conversation.load(
        app_name=request.app_name,
        user=str(user.username),
        name="conversation_brainstorm",
    )
    conversation.remove_last_message_type("architecture")
    conversation.add_system(
        f"Current architecture:\n\n{brainstorm.present_to_llm(config['architecture'])}",
        type_="architecture",
    )
    conversation.persist(
        request.app_name, str(user.username), name="conversation_brainstorm"
    )
