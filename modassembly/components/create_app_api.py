from fastapi import APIRouter, HTTPException
from modassembly.components.create_app import create_app
from modassembly.components.create_app_architecture import create_app_architecture

router = APIRouter()

@router.post("/create-app/")
async def create_app_api(app_name: str):
    """
    Endpoint for creating a new app.
    """
    try:
        # Create the app
        create_app(app_name)
        
        # Set up the app architecture
        create_app_architecture(app_name)
        
        return {"message": f"App '{app_name}' created successfully."}
    
    except FileExistsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="An error occurred while creating the app.")
