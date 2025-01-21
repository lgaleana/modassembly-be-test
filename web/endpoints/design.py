from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.logging.get_user_activity_logs import get_user_activity_logs
from app.models.User import User
from utils.config.architecture import ImplementedComponent
from web.modassembly_web.app.modassembly.authentication.authenticate import authenticate
from workflows import brainstorm
from workflows import design


USAGE_LIMIT = 100


router = APIRouter()


class Request(BaseModel):
    app_name: str
    user_message: str
    architecture: List[ImplementedComponent] = []


@router.post("/chat", response_model=List[Dict[str, Any]])
def chat(request: Request, user: User = Depends(authenticate)) -> List[Dict[str, Any]]:
    logs = get_user_activity_logs(user.username, "brainstorm")
    if len(logs) > USAGE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Usage limit exceeded.",
        )
    return brainstorm.run(request.app_name, request.user_message, str(user.username))


@router.post("/map", response_model=Dict[str, Any])
def map(request: Request, user: User = Depends(authenticate)) -> Dict[str, Any]:
    logs = get_user_activity_logs(user.username, "design")
    if len(logs) > USAGE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Usage limit exceeded.",
        )
    return design.run(
        request.app_name,
        str(user.username),
        request.user_message,
    )
