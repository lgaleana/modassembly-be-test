import json
from typing import Any, Dict, List, Optional, Union, Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from utils.files import File
from utils.io import print_system


class BaseComponent(BaseModel):
    type: str = Field(description="sqlalchemymodel or function")
    name: str = Field(description="The name of the sqlalchemymodel or function")
    namespace: str = Field(description="The namespace of the component")
    pypi_packages: List[str] = Field(
        description="The pypi packages that the component will need"
    )

    @property
    def key(self) -> str:
        return f"{self.namespace}.{self.name}" if self.namespace else self.name


class SQLAlchemyModel(BaseComponent):
    type: Literal["sqlalchemymodel"] = "sqlalchemymodel"
    fields: List[str] = Field(description="The fields of the model")
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


initial_config = {
    "architecture": [
        ImplementedComponent(
            base=Component(
                Function(
                    name="main",
                    namespace="",
                    purpose="The main FastAPI script.",
                    uses=["Other sqlalchemymodels or functions"],
                    pypi_packages=[
                        "fastapi==0.115.6",
                        "pydantic==2.10.3",
                        "python-dotenv==1.0.1",
                        "uvicorn==0.34.0",
                    ],
                    is_endpoint=False,
                )
            )
        ),
        ImplementedComponent(
            base=Component(
                Function(
                    name="get_db",
                    namespace="helpers",
                    purpose="Initializes the database and gets a session.",
                    uses=[],
                    pypi_packages=["psycopg2-binary==2.9.10", "sqlalchemy==2.0.36"],
                    is_endpoint=False,
                )
            )
        ),
    ],
    "external_infrastructure": ["database", "http"],
    "conversation": [],
    "url": None,
}


def load_config(app_name: str) -> Dict[str, Union[str, List[ImplementedComponent]]]:
    with open(f"db/repos/{app_name}/config.json", "r") as f:
        config = json.load(f)
    print_system(json.dumps(config, indent=2))
    return {
        "name": config["name"],
        "architecture": [
            ImplementedComponent.model_validate(a) for a in config["architecture"]
        ],
        "external_infrastructure": config["external_infrastructure"],
        "stories": config["stories"],
        "url": config["url"],
    }


def save_config(config: Dict[str, Union[str, List[ImplementedComponent]]]) -> None:
    assert isinstance(config["architecture"], List)
    raw_architecture = [c.model_dump() for c in config["architecture"]]
    raw_config = {
        "name": config["name"],
        "architecture": raw_architecture,
        "external_infrastructure": config["external_infrastructure"],
        "stories": config["stories"],
        "url": config["url"],
    }
    print_system(json.dumps(raw_config, indent=2))
    with open(f"db/repos/{config['name']}/config.json", "w") as f:
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


def create_initial_config(app_name: str):
    config = initial_config.copy()
    config["name"] = app_name
    save_config(config)
