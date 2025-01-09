from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.models.User import User
from app.logging.get_user_activity_logs import get_user_activity_logs
from utils.config.architecture import ImplementedComponent
from web.modassembly_web.app.modassembly.authentication.authenticate import authenticate
from workflows import implement


USAGE_LIMIT = 50


router = APIRouter()


class Request(BaseModel):
    app_name: str
    architecture: List[ImplementedComponent] = []


@router.post("", response_model=Dict[str, Any])
def implement_architecture(
    request: Request, user: User = Depends(authenticate)
) -> Dict[str, Any]:
    logs = get_user_activity_logs(user.username, "design")
    if len(logs) > USAGE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Usage limit exceeded.",
        )
    return implement.run(request.app_name, str(user.username))
