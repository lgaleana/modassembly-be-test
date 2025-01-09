from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.logging.get_user_activity_logs import get_user_activity_logs
from app.models.User import User
from utils.architecture import ImplementedComponent
from web.modassembly_web.app.modassembly.authentication.authenticate import authenticate
from workflows import design


USAGE_LIMIT = 100


router = APIRouter()


class Request(BaseModel):
    app_name: str
    user_message: str
    architecture: List[ImplementedComponent] = []


class Response(BaseModel):
    config: Dict[str, Any]
    conversation: List[Dict[str, Any]]

    model_config = ConfigDict(arbitrary_types_allowed=True)


@router.post("/chat", response_model=Response)
def chat(request: Request, user: User = Depends(authenticate)) -> Response:
    logs = get_user_activity_logs(user.username, "design")
    if len(logs) > USAGE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Usage limit exceeded.",
        )
    config, conversation = design.run(
        request.app_name, request.user_message, str(user.username)
    )
    return Response(config=config, conversation=conversation)
