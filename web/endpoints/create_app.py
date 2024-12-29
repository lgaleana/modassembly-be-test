import os

from fastapi import APIRouter
from pydantic import BaseModel


router = APIRouter()


class Request(BaseModel):
    app_name: str


@router.post("", response_model=None)
async def create(request: Request) -> None:
    if os.path.exists(f"db/repos/{request.app_name}"):
        raise ValueError(f"Application {request.app_name} already exists")
    os.mkdir(f"db/repos/{request.app_name}")
