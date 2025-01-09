import json
from typing import Any, Dict, List, Optional, Union, Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from utils.files import File, REPOS


class BaseComponent(BaseModel):
    type: str = Field(description="dbmodel or function")
    name: str = Field(description="The name of the dbmodel or function")
    namespace: str = Field(
        description="The virtual location of the component, ie, the file path. "
        "Use a dot notation."
    )
    dependencies: List[str] = Field(
        description="The other namespace.dbmodels or "
        "namespace.functions that the actual code of this component depends on"
    )
    pypi_packages: List[str] = Field(description="The pypi packages that it will need")

    @property
    def key(self) -> str:
        return f"{self.namespace}.{self.name}" if self.namespace else self.name


class DBModel(BaseComponent):
    class ModelField(BaseModel):
        name: str = Field(description="The name of the field")
        purpose: str = Field(description="The type of the field")

    type: Literal["dbmodel"] = "dbmodel"
    fields: List[ModelField] = Field(description="The fields of the model")


class Function(BaseComponent):
    type: Literal["function"] = "function"
    purpose: str = Field(description="The purpose of the function")
    is_endpoint: bool = Field(description="Whether this is a FastAPI endpoint")


class Component(RootModel):
    root: Annotated[Union[DBModel, Function], Field(discriminator="type")]

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
            for k, v in DBModel.model_json_schema()["properties"].items()
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
            "enum": ["dbmodel", "function"],
            "description": "The type of component (dbmodel or function)",
        }
        # Combine all properties
        base_schema["properties"].update(sqlalchemy_fields)
        base_schema["properties"].update(function_fields)
        return base_schema


class ImplementedComponent(BaseModel):
    design: Component
    file: Optional[File] = None
    is_deployed: bool = False


def load_config(app_name: str, user: str) -> Dict[str, Any]:
    with open(f"{REPOS}/{user}_{app_name}/config.json", "r") as f:
        config = json.load(f)
    return {
        "name": config["name"],
        "user": config["user"],
        "architecture": [
            ImplementedComponent.model_validate(a) for a in config["architecture"]
        ],
        "external_infrastructure": config["external_infrastructure"],
        "github": config["github"],
        "url": config["url"],
    }


def save_config(config: Dict[str, Any]) -> None:
    assert isinstance(config["architecture"], List)
    raw_architecture = [c.model_dump() for c in config["architecture"]]
    raw_config = {
        "name": config["name"],
        "user": config["user"],
        "architecture": raw_architecture,
        "external_infrastructure": config["external_infrastructure"],
        "github": config["github"],
        "url": config["url"],
    }
    with open(f"{REPOS}/{config['user']}_{config['name']}/config.json", "w") as f:
        json.dump(
            raw_config,
            f,
            indent=2,
        )


def present_to_llm(architecture: List[ImplementedComponent]) -> str:
    return json.dumps(
        [
            {
                "design": component.design.model_dump(),
                "is_deployed": component.is_deployed,
            }
            for component in architecture
        ],
        indent=4,
    )


def update_architecture_diff(
    architecture: List[ImplementedComponent],
    architecture_diff: List[ImplementedComponent],
) -> None:
    for component in architecture_diff:
        found = False
        for i, existing_component in enumerate(architecture):
            if component.design.key == existing_component.design.key:
                architecture[i] = component
                found = True
                break
        if not found:
            architecture.append(component)
