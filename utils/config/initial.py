from copy import deepcopy
from typing import Any, Dict, List

from utils.config.architecture import (
    Component,
    DBModel,
    Function,
    ImplementedComponent,
    save_config,
)


initial_config = {
    "architecture": [
        ImplementedComponent(
            design=Component(
                Function(
                    name="main",
                    namespace="",
                    purpose="The main FastAPI script.",
                    dependencies=["Other dbmodels or functions"],
                    is_endpoint=False,
                    pypi_packages=[
                        "fastapi==0.115.6",
                        "mypy==1.14.0",
                        "pydantic==2.10.4",
                        "python-dotenv==1.0.1",
                        "python-multipart==0.0.20",
                        "uvicorn==0.34.0",
                    ],
                )
            )
        ),
    ],
    "external_infrastructure": ["www"],
    "url": None,
}


sql_components = [
    ImplementedComponent(
        design=Component(
            Function(
                name="get_sql_session",
                namespace="modassembly.database.sql",
                purpose="1) Initializes the Postgres database. 2) Gets a session.",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=["psycopg2-binary==2.9.10", "sqlalchemy==2.0.36"],
            )
        )
    ),
]

nosql_components = [
    ImplementedComponent(
        design=Component(
            Function(
                name="get_firestore_client",
                namespace="modassembly.database.nosql",
                purpose="1) Initializes the Firestore client. 2) Returns it.",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=["google-cloud-firestore==2.19.0"],
            )
        )
    ),
]

storage_components = [
    ImplementedComponent(
        design=Component(
            Function(
                name="get_gcs_bucket",
                namespace="modassembly.storage",
                purpose="1) Initializes the GCS client. 2) Creates a bucket if it doesn't exist. 3) Returns it.",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=["google-cloud-storage==2.19.0"],
            )
        )
    ),
]


auth_components = [
    ImplementedComponent(
        design=Component(
            DBModel(
                name="User",
                namespace="models",
                fields=[
                    DBModel.ModelField(name="id", purpose="Primary key, autoincrement"),
                    DBModel.ModelField(
                        name="email",
                        purpose="The email of the user, indexed, can't be null",
                    ),
                    DBModel.ModelField(
                        name="hashed_password",
                        purpose="The hashed password, can't be null",
                    ),
                    DBModel.ModelField(
                        name="username",
                        purpose="The username, indexed, can't be null",
                    ),
                ],
                dependencies=[],
                pypi_packages=["sqlalchemy==2.0.36"],
            )
        )
    ),
    ImplementedComponent(
        design=Component(
            Function(
                name="create_access_token",
                namespace="modassembly.authentication",
                purpose="1) Encodes a JWT token using the user's email and an expiration time.",
                dependencies=[],
                is_endpoint=False,
                pypi_packages=["pyjwt==2.10.1"],
            )
        )
    ),
    ImplementedComponent(
        design=Component(
            Function(
                name="authenticate",
                namespace="modassembly.authentication",
                purpose="1) Decodes the JWT token. 2) Retrieves an user. IMPORTANT: Used by the endpoints for authentication.",
                dependencies=["models.User"],
                is_endpoint=False,
                pypi_packages=[
                    "pyjwt==2.10.1",
                    "fastapi==0.115.6",
                    "sqlalchemy==2.0.36",
                ],
            )
        )
    ),
    ImplementedComponent(
        design=Component(
            Function(
                name="verify_user",
                namespace="modassembly.authentication",
                purpose="1) Gets the user from the username. 2) Verifies the password.",
                dependencies=[
                    "models.User",
                ],
                is_endpoint=False,
                pypi_packages=[
                    "bcrypt==4.0.1",
                    "passlib==1.7.4",
                    "sqlalchemy==2.0.36",
                ],
            )
        )
    ),
    ImplementedComponent(
        design=Component(
            Function(
                name="login_api",
                namespace="modassembly.authentication",
                purpose="Logs in an user, given their credentials. 1) Verifies the user. 2) Creates a new JWT token. 3) Returns the token. Use OAuth2PasswordRequestForm.",
                dependencies=[
                    "modassembly.database.sql.get_sql_session",
                    "modassembly.authentication.verify_user",
                    "modassembly.authentication.create_access_token",
                ],
                is_endpoint=True,
                pypi_packages=[
                    "fastapi==0.115.6",
                    "pydantic[email]==2.10.4",
                    "sqlalchemy==2.0.36",
                ],
            )
        )
    ),
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

    if "sql" in external_infrastructure:
        config["architecture"].extend(sql_components)
        if "authentication" in external_infrastructure:
            config["architecture"].extend(auth_components)
    if "nosql" in external_infrastructure:
        config["architecture"].extend(nosql_components)
    if "storage" in external_infrastructure:
        config["architecture"].extend(storage_components)
    config["external_infrastructure"] = external_infrastructure
    config["github"] = github_url
    save_config(config)
    return config
