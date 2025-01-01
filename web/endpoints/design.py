from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from utils.state import Conversation
from workflows import design


router = APIRouter()


class Request(BaseModel):
    app_name: str
    user_story: str


class Response(BaseModel):
    config: Dict[str, Any]
    conversation: Conversation

    model_config = ConfigDict(arbitrary_types_allowed=True)


@router.post("/chat", response_model=Response)
async def chat(request: Request) -> Response:
    config, conversation = design.run(request.app_name, request.user_story)
    return Response(config=config, conversation=conversation)
