import shutil
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.models.User import User
from utils.github import delete_github_repository
from web.modassembly_web.app.modassembly.authentication.authenticate import authenticate
from workflows.helpers import REPOS, create_app

router = APIRouter()


class Request(BaseModel):
    app_name: str
    external_infrastructure: List[str] = ["www", "sql"]


@router.post("", response_model=Dict[str, Any])
def create(request: Request, user: User = Depends(authenticate)) -> Dict[str, Any]:
    return create_app(
        request.app_name, request.external_infrastructure, str(user.username)
    )


@router.delete("", response_model=None)
def delete(app_name: str, user: User = Depends(authenticate)) -> None:
    repo_name = f"{user.username}_{app_name}".replace(" ", "-")
    delete_github_repository(repo_name)
    shutil.rmtree(f"{REPOS}/{repo_name}")
