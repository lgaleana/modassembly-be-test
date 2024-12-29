from fastapi import APIRouter
from pydantic import BaseModel

from utils.architecture import load_config
from workflows import implement

router = APIRouter()


class Request(BaseModel):
    app_name: str


@router.post("", response_model=str)
async def implement_architecture(request: Request) -> str:
    config = load_config(request.app_name)
    return implement.run(config, request.app_name)
