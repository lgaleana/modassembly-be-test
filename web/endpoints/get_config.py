from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from utils.architecture import load_config
from utils.state import Conversation


router = APIRouter()


class Response(BaseModel):
    config: Dict[str, Any]
    conversation: Conversation

    model_config = ConfigDict(arbitrary_types_allowed=True)


@router.get("", response_model=Response)
async def get_config(app_name: str) -> Response:
    conversation = Conversation.load(app_name)
    return Response(config=load_config(app_name), conversation=conversation)
