from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.models.User import User
from utils.architecture import ImplementedComponent
from web.modassembly_web.app.modassembly.authentication.authenticate import authenticate
from workflows import design


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
    config, conversation = design.run(
        request.app_name, request.user_message, request.architecture, str(user.username)
    )
    return Response(config=config, conversation=conversation)
