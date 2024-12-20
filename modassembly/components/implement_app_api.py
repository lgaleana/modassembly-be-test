from fastapi import APIRouter, HTTPException

from workflows.run import run

router = APIRouter()


@router.get("/implement_app")
async def implement_app_api(app_name: str):
    service_url = run(app_name)
    return service_url
