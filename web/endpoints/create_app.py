from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from workflows.helpers import create_app

router = APIRouter()


class Request(BaseModel):
    app_name: str
    external_infrastructure: List[str] = ["http", "database"]


@router.post("", response_model=Dict[str, Any])
async def create(request: Request) -> Dict[str, Any]:
    return create_app(request.app_name, request.external_infrastructure)
