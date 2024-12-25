from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from workflows.run import run

router = APIRouter()


class ImplementArchitectureRequest(BaseModel):
    app_name: str


@router.post("/implement-architecture", response_model=str)
async def implement_architecture(request: ImplementArchitectureRequest):
    return run(request.app_name)
