import json
from typing import Any, Dict, List, Optional, Union, Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from utils.files import File, REPOS
from utils.io import print_system


class BaseComponent(BaseModel):
    type: str = Field(description="sqlalchemymodel or function")
    name: str = Field(description="The name of the sqlalchemymodel or function")
    namespace: str = Field(
        description="The virtual location of the component, ie, the file path. "
        "Use a dot notation."
    )
    pypi_packages: List[str] = Field(description="The pypi packages that it will need")

    @property
    def key(self) -> str:
        return f"{self.namespace}.{self.name}" if self.namespace else self.name


class SQLAlchemyModel(BaseComponent):
    class ModelField(BaseModel):
        name: str = Field(description="The name of the field")
        purpose: str = Field(description="The type of the field")

    type: Literal["sqlalchemymodel"] = "sqlalchemymodel"
    fields: List[ModelField] = Field(description="The fields of the model")
    associations: List[str] = Field(
        description="The other sqlalchemymodels that this model is associated with"
    )


class Function(BaseComponent):
    type: Literal["function"] = "function"
    purpose: str = Field(description="The purpose of the function")
    uses: List[str] = Field(
        description="The sqlalchemymodels or functions that this component uses internally"
    )
    is_endpoint: bool = Field(description="Whether this is a FastAPI endpoint")


class Component(RootModel):
    root: Annotated[Union[SQLAlchemyModel, Function], Field(discriminator="type")]

    @property
    def key(self) -> str:
        return self.root.key

    @classmethod
    def model_json_schema(cls) -> Dict[str, Any]:
        """Returns a simplified schema suitable for OpenAI function calls"""
        # Get base schema (common fields for all components)
        base_schema = BaseComponent.model_json_schema()
        # Get type-specific fields from each subclass
        sqlalchemy_fields = {
            k: v
            for k, v in SQLAlchemyModel.model_json_schema()["properties"].items()
            if k not in base_schema["properties"]
        }
        function_fields = {
            k: v
            for k, v in Function.model_json_schema()["properties"].items()
            if k not in base_schema["properties"]
        }
        # Update the type field to be an enum of possible values
        base_schema["properties"]["type"] = {
            "type": "string",
            "enum": ["sqlalchemymodel", "function"],
            "description": "The type of component (sqlalchemymodel or function)",
        }
        # Combine all properties
        base_schema["properties"].update(sqlalchemy_fields)
        base_schema["properties"].update(function_fields)
        return base_schema


class ImplementedComponent(BaseModel):
    base: Component
    file: Optional[File] = None


def load_config(app_name: str) -> Dict[str, Any]:
    with open(f"{REPOS}/{app_name}/config.json", "r") as f:
        config = json.load(f)
    print_system(json.dumps(config, indent=2))
    return {
        "name": config["name"],
        "architecture": [
            ImplementedComponent.model_validate(a) for a in config["architecture"]
        ],
        "pypi_packages": config["pypi_packages"],
        "external_infrastructure": config["external_infrastructure"],
        "github": config["github"],
        "url": config["url"],
    }


def save_config(config: Dict[str, Any]) -> None:
    assert isinstance(config["architecture"], List)
    raw_architecture = [c.model_dump() for c in config["architecture"]]
    raw_config = {
        "name": config["name"],
        "architecture": raw_architecture,
        "pypi_packages": config["pypi_packages"],
        "external_infrastructure": config["external_infrastructure"],
        "github": config["github"],
        "url": config["url"],
    }
    print_system(json.dumps(raw_config, indent=2))
    with open(f"{REPOS}/{config['name']}/config.json", "w") as f:
        json.dump(
            raw_config,
            f,
            indent=2,
        )


def update_architecture_diff(
    architecture: List[ImplementedComponent],
    architecture_diff: List[ImplementedComponent],
) -> None:
    for component in architecture_diff:
        found = False
        for i, existing_component in enumerate(architecture):
            if component.base.key == existing_component.base.key:
                architecture[i] = component
                found = True
                break
        if not found:
            architecture.append(component)


initial_config = {
    "architecture": [
        ImplementedComponent(
            base=Component(
                Function(
                    name="main",
                    namespace="",
                    purpose="The main FastAPI script.",
                    uses=["Other sqlalchemymodels or functions"],
                    is_endpoint=False,
                    pypi_packages=[
                        "fastapi==0.115.6",
                        "pydantic==2.10.4",
                        "python-dotenv==1.0.1",
                        "python-multipart==0.0.20",
                        "uvicorn==0.34.0",
                    ],
                )
            )
        ),
    ],
    "pypi_packages": None,
    "external_infrastructure": ["http"],
    "url": None,
}


db_components = [
    ImplementedComponent(
        base=Component(
            Function(
                name="get_session",
                namespace="modassembly.database",
                purpose="1) Initializes the Postgres database. 2) Gets a session.",
                uses=[],
                is_endpoint=False,
                pypi_packages=["psycopg2-binary==2.9.10", "sqlalchemy==2.0.36"],
            )
        )
    ),
]


auth_components = [
    ImplementedComponent(
        base=Component(
            SQLAlchemyModel(
                name="User",
                namespace="models",
                fields=[
                    SQLAlchemyModel.ModelField(
                        name="id", purpose="Primary key, autoincremental"
                    ),
                    SQLAlchemyModel.ModelField(
                        name="email", purpose="The email of the user, can't be null"
                    ),
                    SQLAlchemyModel.ModelField(
                        name="password",
                        purpose="The hashed password, can't be null",
                    ),
                    SQLAlchemyModel.ModelField(
                        name="role", purpose='"user" or "admin", default to "user"'
                    ),
                ],
                associations=[],
                pypi_packages=["sqlalchemy==2.0.36"],
            )
        )
    ),
    ImplementedComponent(
        base=Component(
            Function(
                name="create_access_token",
                namespace="modassembly.authentication.core",
                purpose="1) Encodes a JWT token using the user's email and an expiration time.",
                uses=[],
                is_endpoint=False,
                pypi_packages=["pyjwt==2.10.1"],
            )
        )
    ),
    ImplementedComponent(
        base=Component(
            Function(
                name="authenticate",
                namespace="modassembly.authentication.core",
                purpose="1) Decodes the JWT token. 2) Retrieves an user. IMPORTANT: Used by the endpoints for authentication.",
                uses=["models.User"],
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
        base=Component(
            Function(
                name="login_api",
                namespace="modassembly.authentication.endpoints",
                purpose="Logs in an user. 1) Gets the user. 2) Verifies the password. 3) Creates a new JWT token.",
                uses=[
                    "modassembly.database.get_session",
                    "models.User",
                    "modassembly.authentication.core.create_access_token",
                ],
                is_endpoint=True,
                pypi_packages=[
                    "bcrypt==4.0.1",
                    "fastapi==0.115.6",
                    "passlib==1.7.4",
                    "pydantic==2.10.4",
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
) -> Dict[str, Any]:
    config = initial_config.copy()
    config["name"] = app_name

    if "database" in external_infrastructure:
        config["architecture"].extend(db_components)
        if "authentication" in external_infrastructure:
            config["architecture"].extend(auth_components)
    config["external_infrastructure"] = external_infrastructure
    config["github"] = github_url
    save_config(config)
    return config
