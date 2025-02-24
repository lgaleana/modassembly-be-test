from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from utils.config.architecture import ImplementedComponent
from web.modassembly_web.app.modassembly.authentication.authenticate import authenticate
from workflows import implement
from workflows import sync


USAGE_LIMIT = 50


router = APIRouter()


class Request(BaseModel):
    app_name: str
    architecture: List[ImplementedComponent] = []


@router.post("", response_model=Dict[str, Any])
def implement_architecture(
    request: Request, user = Depends(authenticate)
) -> Dict[str, Any]:
    return implement.run(request.app_name, str(user.username))


@router.post("/sync", response_model=Dict[str, Any])
def sync_architecture(
    request: Request, user = Depends(authenticate)
) -> Dict[str, Any]:
    return sync.run(request.app_name, str(user.username))
