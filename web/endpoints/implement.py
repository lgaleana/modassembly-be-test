from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from utils.architecture import ImplementedComponent, load_config
from workflows import implement

router = APIRouter()


class Request(BaseModel):
    app_name: str
    architecture: List[ImplementedComponent] = []


@router.post("", response_model=str)
async def implement_architecture(request: Request) -> str:
    return implement.run(request.app_name, request.architecture)
