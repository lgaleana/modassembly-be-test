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
            )
        ),
        ImplementedComponent(
            design=Component(
                Function(
                    name="main",
                    namespace="app",
                    purpose="The main FastAPI script.",
                    dependencies=["Other datamodels or functions"],
                    is_endpoint=False,
                    pypi_packages=[
                        "fastapi",
                        "mypy",
                        "pydantic",
                        "python-dotenv",
                        "python-multipart",
                        "uvicorn",
                    ],
                )
            )
        ),
    ],
    "url": None,
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
                purpose="1) Initializes the Postgres database. Uses the DB_URL environment variable. 2) Gets a session.",
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
                purpose="1) Initializes the GCS client. Uses the GCS_BUCKET environment variable. 2) Creates a bucket if it doesn't exist. 3) Returns it.",
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
                purpose="1) Initializes the Cloud Tasks client. 2) Creates a Tasks queue 3) Returns the client.",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=["google-cloud-tasks"],
            ),
            Function(
                name="get_gcp_tasks_queue",
                namespace="app.modassembly.tasks",
                purpose="1) Gets the Tasks queue. Uses environment variables. 2) Returns it.",
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
        "name": "EmailClient",
        "namespace": "External",
        "description": "A very basic email client for sending emails.",
        "added_functions": [
            Function(
                name="get_email_client",
                namespace="app.modassembly.email",
                purpose="1) Initializes the client. Uses environment variables. 2) Returns it.",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=[],
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
    config = deepcopy(initial_config)
    config["name"] = app_name
    config["user"] = user
    config["github"] = github_url
    save_config(config)
    return config
