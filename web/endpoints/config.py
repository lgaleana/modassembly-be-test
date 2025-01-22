from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.models.User import User
from app.modassembly.authentication.authenticate import authenticate
from utils.config.architecture import load_config

router = APIRouter()


@router.get("", response_model=Dict[str, Any])
def get(app_name: str, user: User = Depends(authenticate)) -> Dict[str, Any]:
    return load_config(app_name, user.username)
