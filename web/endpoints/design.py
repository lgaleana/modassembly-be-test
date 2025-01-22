from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.logging.get_user_activity_logs import get_user_activity_logs
from app.models.User import User
from utils.config.architecture import ImplementedComponent
from utils.state import Conversation
from web.modassembly_web.app.modassembly.authentication.authenticate import authenticate
from workflows import brainstorm
from workflows import design


CHAT_LIMIT = 100
MAP_LIMIT = 50


router = APIRouter()


class Request(BaseModel):
    app_name: str
    user_message: str
    architecture: List[ImplementedComponent] = []


@router.post("/chat", response_model=List[Dict[str, Any]])
def chat(request: Request, user: User = Depends(authenticate)) -> List[Dict[str, Any]]:
    logs = get_user_activity_logs(user.username, "brainstorm")
    if len(logs) > CHAT_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Usage limit exceeded.",
        )
    return brainstorm.run(request.app_name, request.user_message, str(user.username))


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


@router.post("/sync")
def sync(request: Request, user: User = Depends(authenticate)) -> None:
    logs = get_user_activity_logs(user.username, "brainstorm")
    if len(logs) > MAP_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Usage limit exceeded.",
        )
    design.run(
        request.app_name,
        str(user.username),
        request.user_message,
        message_type="sync",
    )
