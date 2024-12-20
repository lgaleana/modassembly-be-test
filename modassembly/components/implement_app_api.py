from fastapi import APIRouter, HTTPException

from workflows.run import run

router = APIRouter()


@router.get("/implement_app")
async def implement_app_api(app_name: str):
    """
    Endpoint for implementing an app.
    """
    try:
        # Call the implement_app function
        service_url = run(app_name)
        return service_url
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="An error occurred while implementing the app."
        )
