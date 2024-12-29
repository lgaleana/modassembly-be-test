import os

from fastapi import APIRouter
from pydantic import BaseModel

from utils.architecture import create_initial_config, load_config
from workflows.helpers import REPOS
from workflows import design


router = APIRouter()


class Request(BaseModel):
    app_name: str
    user_story: str


@router.post("/chat", response_model=str)
async def chat(request: Request) -> str:
    if not os.path.exists(f"{REPOS}/{request.app_name}/config.json"):
        create_initial_config(request.app_name)
    config = load_config(request.app_name)
    return design.run(config, request.user_story)
