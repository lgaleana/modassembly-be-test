from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from utils.architecture import load_config
from workflows import design


router = APIRouter()


class Request(BaseModel):
    app_name: str
    user_story: str


@router.post("/chat", response_model=Dict[str, Any])
async def chat(request: Request) -> Dict[str, Any]:
    config = load_config(request.app_name)
    return design.run(config, request.user_story)
