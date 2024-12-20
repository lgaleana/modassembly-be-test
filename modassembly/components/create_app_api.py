from fastapi import APIRouter, HTTPException
from modassembly.components.create_app import create_app
from modassembly.components.create_app_architecture import create_app_architecture

router = APIRouter()


@router.post("/create-app/")
async def create_app_api(app_name: str):
    create_app(app_name)
    return create_app_architecture(app_name)
