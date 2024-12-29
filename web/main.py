from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

from web.endpoints.create_app import router as create_app_router
from web.endpoints.design import router as design_router
from web.endpoints.implement import router as implement_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(create_app_router, prefix="/create-app")
app.include_router(design_router, prefix="/design")
app.include_router(implement_router, prefix="/implement")
