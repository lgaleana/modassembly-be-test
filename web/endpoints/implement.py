from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from utils.architecture import ImplementedComponent
from web.modassembly_web.app.modassembly.authentication.authenticate import authenticate
from web.modassembly_web.app.models.User import User
from workflows import implement

router = APIRouter()


class Request(BaseModel):
    app_name: str
    architecture: List[ImplementedComponent] = []


@router.post("", response_model=Dict[str, Any])
def implement_architecture(
    request: Request, user: User = Depends(authenticate)
) -> Dict[str, Any]:
    return implement.run(request.app_name, request.architecture, str(user.username))
