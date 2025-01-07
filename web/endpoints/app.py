import shutil
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from utils.github import delete_github_repository
from workflows.helpers import REPOS, create_app

router = APIRouter()


class Request(BaseModel):
    app_name: str
    external_infrastructure: List[str] = ["www", "sql"]


@router.post("", response_model=Dict[str, Any])
def create(request: Request) -> Dict[str, Any]:
    return create_app(request.app_name, request.external_infrastructure)


@router.delete("", response_model=None)
def delete(app_name: str) -> None:
    delete_github_repository(app_name)
    shutil.rmtree(f"{REPOS}/{app_name}")
