from copy import deepcopy
from typing import Any, Dict, List

from utils.config.architecture import (
    Component,
    Function,
    Infrastructure,
    ImplementedComponent,
    save_config,
)


initial_config = {
    "architecture": [
        ImplementedComponent(
            design=Component(
                root=Infrastructure(
                    name="CloudRun",
                    namespace="External",
                    config={},
                )
            ),
            update_status="up_to_date",
        ),
        ImplementedComponent(
            design=Component(
                Function(
                    name="main",
                    namespace="app",
                    purpose="1) Calls load_dotenv().\n"
                    "2) Initializes the FastAPI app.\n"
                    "3) Adds CORSMiddleware with *.\n"
                    "4) Adds all the application routers.\n"
                    "5) Adds all the application models.\n"
                    "6) Calls Base.metadata.create_all(engine).",
                    dependencies=["Other datamodels or functions"],
                    is_endpoint=False,
                    pypi_packages=[
                        "fastapi==0.115.6",
                        "mypy==1.15.0",
                        "pydantic==2.10.4",
                        "python-dotenv==1.0.1",
                        "uvicorn==0.34.0",
                    ],
                )
            ),
            update_status="up_to_date",
        ),
    ],
}


AVAILABLE_INFRASTRUCTURE = [
    {
        "name": "CloudRun",
        "namespace": "External",
        "description": "A Google Cloud Run web service.",
        "added_functions": [],
    },
    {
        "name": "CloudSQL",
        "namespace": "External",
        "description": "A Google Cloud SQL database. Used with datamodels.",
        "added_functions": [
            Function(
                name="get_sql_session",
                namespace="app.modassembly.database.sql",
                purpose="1) Initializes Base, engine and SessionLocal. Uses the DB_URL environment variable.\n"
                "2) Yields a SessionLocal instance.",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=["psycopg2-binary", "sqlalchemy"],
            )
        ],
    },
    {
        "name": "CloudStorage",
        "namespace": "External",
        "description": "A Google Cloud Storage bucket to save/read files.",
        "added_functions": [
            Function(
                name="get_gcs_bucket",
                namespace="app.modassembly.storage",
                purpose="1) Reads from the environment variable GCS_BUCKET.\n2) Creates a global bucket if it doesn't exist.\n3) Returns it.",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=["google-cloud-storage"],
            )
        ],
    },
    {
        "name": "CloudTasks",
        "namespace": "External",
        "description": "A Google Cloud Tasks queue. IMPORTANT: Triggers an http endpoint.",
        "added_functions": [
            Function(
                name="get_gcp_tasks_client",
                namespace="app.modassembly.tasks",
                purpose="1) Creates a global Cloud Tasks client if it doesn't exist.\n2) Returns it.",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=["google-cloud-tasks"],
            ),
            Function(
                name="get_gcp_tasks_queue",
                namespace="app.modassembly.tasks",
                purpose="1) Calls get_gcp_tasks_client.\n2) Returns the queue_path. Reads from environment variables GCP_PROJECT, GCP_LOCATION and GCP_QUEUE",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=["google-cloud-tasks"],
            ),
        ],
    },
    {
        "name": "CloudScheduler",
        "namespace": "External",
        "description": "A Google Cloud Scheduler job. IMPORTANT: Triggers an http endpoint.",
        "added_functions": [],
    },
    {
        "name": "Firestore",
        "namespace": "External",
        "description": "A Google Cloud Firestore database.",
        "added_functions": [
            Function(
                name="get_firestore_database",
                namespace="app.modassembly.database.nosql",
                purpose="1) Creates a global Firestore client if it doesn't exist. Uses the environment variable FIRESTORE_DB.\n2) Returns the client.",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=["google-cloud-firestore"],
            )
        ],
    },
]


def create_initial_config(
    app_name: str,
    external_infrastructure: List[str],
    github_url: str,
    user: str,
) -> Dict[str, Any]:
    config: Dict[str, Any] = deepcopy(initial_config)
    config["name"] = app_name
    config["user"] = user
    config["github"] = github_url
    save_config(config)
    return config
