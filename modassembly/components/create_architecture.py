import os
from typing import Dict, Any

from fastapi import APIRouter
from pydantic import BaseModel

from workflows.architecture import run

router = APIRouter()


class ArchitectureRequest(BaseModel):
    app_name: str
    system_description: str


@router.post("/create-architecture", response_model=Dict[str, Any])
async def create_architecture(request: ArchitectureRequest) -> Dict[str, Any]:
    if os.path.exists(f"db/repos/{request.app_name}"):
        raise ValueError(f"Application {request.app_name} already exists")
    return run(request.app_name, request.system_description)
