from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.models.User import User
from app.modassembly.authentication.authenticate import authenticate
from utils.state import Conversation

router = APIRouter()


@router.get("", response_model=List[Dict[str, Any]])
def get(
    app_name: str, tag: str, user: User = Depends(authenticate)
) -> List[Dict[str, Any]]:
    return Conversation.load(app_name, user.username, name=f"conversation_{tag}")
