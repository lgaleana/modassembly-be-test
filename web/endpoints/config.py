from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.models.User import User
from app.modassembly.authentication.authenticate import authenticate
from utils.config.architecture import (
    Component,
    Function,
    Infrastructure,
    ImplementedComponent,
    Service,
    load_all_configs,
    load_config,
    save_config,
)

router = APIRouter()


@router.get("", response_model=Dict[str, Any])
def get(app_name: str, user: User = Depends(authenticate)) -> Dict[str, Any]:
    return load_config(app_name, user.username)


class SaveRequest(BaseModel):
    config: Dict[str, Any]


@router.post("", response_model=Dict[str, Any])
def save(request: SaveRequest, user: User = Depends(authenticate)) -> Dict[str, Any]:
    architecture = [
        ImplementedComponent.model_validate(c) for c in request.config["architecture"]
    ]
    request.config["architecture"] = architecture
    save_config(request.config)
    return request.config


@router.get("/all", response_model=List[str])
def get_all(user: User = Depends(authenticate)) -> List[str]:
    return [c["name"] for c in load_all_configs(user.username)]


@router.get("/all/infrastructure", response_model=List[str])
def get_all_infrastructure(user: User = Depends(authenticate)) -> List[str]:
    return [
        "CloudSQL Database",
        "CloudStorage Bucket",
        "CloudTasks Queue",
        "CloudScheduler Job",
    ]


class InfrastructureRequest(BaseModel):
    app_name: str
    infrastructure_to_add: str


@router.post("/integrate/infrastructure", response_model=Dict[str, Any])
def integrate_infrastructure(
    request: InfrastructureRequest, user: User = Depends(authenticate)
) -> Dict[str, Any]:
    config = load_config(request.app_name, user.username)
    config["architecture"].extend(
        [
            ImplementedComponent(
                design=Component(
                    Infrastructure(
                        name="CloudSQL",
                        namespace="External",
                        config={},
                    )
                ),
                update_status="up_to_date",
            ),
        ]
    )
    save_config(config)
    return config


class RepositoryRequest(BaseModel):
    app_name: str
    repository_to_add: str


@router.post("/integrate/repository", response_model=Dict[str, Any])
def integrate_repository(
    request: RepositoryRequest, user: User = Depends(authenticate)
) -> Dict[str, Any]:
    config = load_config(request.app_name, user.username)
    config_to_add = load_config(request.repository_to_add, user.username)

    for component in config["architecture"]:
        if (
            isinstance(component.design.root, Service)
            and component.design.root.name == config_to_add["name"]
        ):
            return config

    service = Service(
        name=config_to_add["name"],
        endpoints=[],
    )
    for component_to_add in config_to_add["architecture"]:
        if (
            isinstance(component_to_add.design.root, Function)
            and component_to_add.design.root.is_endpoint
        ):
            service.endpoints.append(component_to_add.design.root)
    config["architecture"].append(
        ImplementedComponent(
            design=Component(service),
            update_status="up_to_date",
        )
    )
    save_config(config)
    return config
