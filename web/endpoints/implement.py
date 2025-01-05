from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from utils.architecture import ImplementedComponent
from workflows import implement

router = APIRouter()


class Request(BaseModel):
    app_name: str
    architecture: List[ImplementedComponent] = []


@router.post("", response_model=Dict[str, Any])
async def implement_architecture(request: Request) -> Dict[str, Any]:
    return implement.run(request.app_name, request.architecture)
