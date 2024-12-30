import os
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from utils.architecture import create_initial_config

router = APIRouter()


class Request(BaseModel):
    app_name: str


@router.post("", response_model=Dict[str, Any])
async def create(request: Request) -> Dict[str, Any]:
    if os.path.exists(f"db/repos/{request.app_name}"):
        raise ValueError(f"Application {request.app_name} already exists")
    os.mkdir(f"db/repos/{request.app_name}")
    return create_initial_config(request.app_name)
