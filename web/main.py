import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

subrepo_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "modassembly_web")
)
sys.path.append(subrepo_path)


from app.modassembly.authentication.login_api import router as login_router
from app.modassembly.database.sql.get_sql_session import (
    Base,
    engine,
)
from web.endpoints.app import router as app_router
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

app.include_router(app_router, prefix="/app")
app.include_router(design_router, prefix="/design")
app.include_router(implement_router, prefix="/implement")
app.include_router(login_router, prefix="")

Base.metadata.create_all(bind=engine)
