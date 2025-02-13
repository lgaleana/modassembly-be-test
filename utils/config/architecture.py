import json
import os
from typing import Any, Dict, List, Optional, Union, Annotated, Literal

from pydantic import BaseModel, Field, RootModel

from utils.files import File, REPOS


class BaseComponent(BaseModel):
    type: Literal["datamodel", "function"]
    name: str
    namespace: str
    dependencies: List[str]

    @property
    def key(self) -> str:
        return f"{self.namespace}.{self.name}" if self.namespace else self.name


class DataModel(BaseComponent):
    class ModelField(BaseModel):
        name: str
        purpose: str

    type: Literal["datamodel"] = "datamodel"
    fields: List[ModelField]


class Function(BaseComponent):
    type: Literal["function"] = "function"
    purpose: str
    pypi_packages: List[str]
    is_endpoint: bool


class Infrastructure(BaseModel):
    type: Literal["infrastructure"] = "infrastructure"
    name: Literal[
        "CloudRun",
        "CloudSQL",
        "CloudStorage",
        "CloudTasks",
        "CloudScheduler",
        "Firestore",
    ]
    namespace: Literal["External"] = "External"
    config: Dict[str, Any] = {}

    @property
    def key(self) -> str:
        return f"{self.namespace}.{self.name}"


class Service(BaseModel):
    type: Literal["microservice"] = "microservice"
    name: str
    namespace: Literal["External"] = "External"
    endpoints: List[Function]

    @property
    def key(self) -> str:
        return f"{self.namespace}.{self.name}"


class Component(RootModel):
    root: Annotated[
        Union[DataModel, Function, Infrastructure, Service], Field(discriminator="type")
    ]

    @property
    def key(self) -> str:
        return self.root.key


class ImplementedComponent(BaseModel):
    design: Component
    file: Optional[File] = None
    update_status: Literal["to_update", "to_remove", "up_to_date", "blocked"] = (
        "to_update"
    )
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
        "github": config["github"],
    }


def save_config(config: Dict[str, Any]) -> None:
    assert isinstance(config["architecture"], List)
    raw_architecture = [c.model_dump() for c in config["architecture"]]
    raw_config = {
        "name": config["name"],
        "user": config["user"],
        "architecture": raw_architecture,
        "github": config["github"],
    }
    with open(f"{REPOS}/{config['user']}_{config['name']}/config.json", "w") as f:
        json.dump(
            raw_config,
            f,
            indent=2,
        )


def load_all_configs(user: str) -> List[Dict[str, Any]]:
    configs = []
    for file in os.listdir(REPOS):
        if f"{user}_" in file:
            configs.append(load_config("_".join(file.split("_")[1:]), user))
    return configs


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
