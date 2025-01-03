import os
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from utils.architecture import create_initial_config
from utils.state import Conversation
from workflows.helpers import REPOS

router = APIRouter()


class Request(BaseModel):
    app_name: str
    external_infrastructure: List[str] = ["http", "database"]


@router.post("", response_model=Dict[str, Any])
async def create(request: Request) -> Dict[str, Any]:
    if os.path.exists(f"{REPOS}/{request.app_name}"):
        raise ValueError(f"Application {request.app_name} already exists")
    os.mkdir(f"{REPOS}/{request.app_name}")
    Conversation().persist(app_name=request.app_name)
    return create_initial_config(request.app_name, request.external_infrastructure)
