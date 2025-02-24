import json
import os
import pathlib
import re
import subprocess
from typing import Any, Dict, List, Set

import matplotlib.pyplot as plt
import networkx as nx
from pydantic import BaseModel
from utils.config.architecture import (
    Function,
    DataModel,
    ImplementedComponent,
    Infrastructure,
    Service,
)
from utils.config.initial import create_initial_config
from utils.github import (
    create_github_repository,
    execute_git_commands,
    protect_repository,
    repository_exists,
)
from utils.io import print_system
from utils.state import Conversation
from utils.static_analysis import (
    RouterNotFoundError,
    extract_imports,
    extract_router_name,
    extract_sqlalchemy_models,
)


REPOS = os.path.expanduser("~/repos")


MODASSEMBLY_COMPONENTS = {
    "app.main": "app/main.py",
    "app.modassembly.database.sql.get_sql_session": "app/modassembly/database/sql/get_sql_session.py",
    "app.modassembly.storage.get_gcs_bucket": "app/modassembly/storage/get_gcs_bucket.py",
    "app.modassembly.tasks.get_gcp_tasks_client": "app/modassembly/tasks/get_gcp_tasks_client.py",
    "app.modassembly.tasks.get_gcp_tasks_queue": "app/modassembly/tasks/get_gcp_tasks_queue.py",
    "app.modassembly.database.nosql.get_firestore_database": "app/modassembly/database/nosql/get_firestore_database.py",
}


class PatternNotFoundError(Exception):
    pass


def extract_from_pattern(response: str, *, pattern: str) -> List[str]:
    matches = re.findall(pattern, response, re.DOTALL)
    if not matches:
        raise PatternNotFoundError(f"No matches found for pattern :: {pattern}")
    for match in matches:
        print_system(match)
    return matches


def extract_json(response: str) -> List[Any]:
    json_str = extract_from_pattern(response, pattern=r"```json\n(.*?)```")
    json_str = [s.replace("None", "null") for s in json_str]
    return [json.loads(json_str) for json_str in json_str]


def create_app(
    app_name: str,
    external_infrastructure: List[str],
    user: str,
) -> Dict[str, Any]:
    repo_name = f"{user}_{app_name}".replace(" ", "-")
    if repository_exists(repo_name):
        raise ValueError(f"Repository {repo_name} already exists")

    os.mkdir(f"{REPOS}/{repo_name}")
    for file in [".gitignore", "README.md"]:
        with open(f"{REPOS}/fastapi-template/{file}", "r") as f1, open(
            f"{REPOS}/{repo_name}/{file}", "w"
        ) as f2:
            f2.write(f1.read())

    Conversation().persist(app_name, user, name="conversation_brainstorm")
    Conversation().persist(app_name, user, name="conversation_architecture")

    print_system("Initializing git and github...")
    github_url = create_github_repository(repo_name)
    config = create_initial_config(app_name, external_infrastructure, github_url, user)
    execute_git_commands(
        [
            ["git", "init"],
            ["git", "add", "."],
            ["git", "commit", "-m", "first commit"],
            ["git", "branch", "-M", "main"],
            [
                "git",
                "remote",
                "add",
                "origin",
                f"git@github.com:Modular-Asembly/{repo_name}.git",
            ],
            ["git", "push", "-u", "origin", "main"],
        ],
        repo=repo_name,
    )
    protect_repository(repo_name)
    print_system("Success")
    return config


def get_architecture_to_update(
    saved_architecture: List[ImplementedComponent],
    new_architecture: List[ImplementedComponent],
) -> Dict[str, ImplementedComponent]:
    architecture_to_update = {}
    for component in saved_architecture:
        if not component.file:
            architecture_to_update[component.design.key] = component
    for updated_component in new_architecture:
        for old_component in saved_architecture:
            if (
                updated_component.design.key not in MODASSEMBLY_COMPONENTS
                and updated_component.design.key == old_component.design.key
                and updated_component.design.root != old_component.design.root
            ):
                architecture_to_update[updated_component.design.key] = updated_component
                break
    for component_key in architecture_to_update:
        print_system(f"Will update :: {component_key}")
    print_system()
    return architecture_to_update


def group_nodes_by_dependencies(
    architecture: List[ImplementedComponent],
) -> List[Set[str]]:
    levels = []
    dependencies = {}
    for component in architecture:
        if isinstance(component.design.root, DataModel) or isinstance(
            component.design.root, Function
        ):
            dependencies[component.design.root.key] = component.design.root.dependencies

    remaining_components = set(dependencies.keys())
    while remaining_components:
        current_level = {
            component
            for component in remaining_components
            if all(dep not in remaining_components for dep in dependencies[component])
        }

        if not current_level:
            raise ValueError("Circular dependency detected")

        levels.append(current_level)
        remaining_components -= current_level

    return levels


def update_main(
    app_name: str,
    architecture: List[ImplementedComponent],
) -> None:
    with open(f"{REPOS}/{app_name}/app/main.py", "r") as f:
        main_content = f.read()

    models = get_model_modules(app_name, [])
    main_content += "\n# Models\n\n"
    for model in models:
        main_content += f"from {model.module} import {model.name}\n"

    main_content += "\n# Endpoints\n\n"
    for component in architecture:
        if (
            isinstance(component.design.root, Function)
            and component.design.root.is_endpoint
        ):
            for file in component.files:
                import_ = file.path.replace(".py", "").replace("/", ".")
                try:
                    router_name = extract_router_name(file.content)
                    main_content += f"from {import_} import {router_name}\n"
                    main_content += f"app.include_router({router_name})\n"
                except RouterNotFoundError:
                    pass

    if len(models) > 0:
        main_content += "\n# Database\n\n"
        main_content += (
            "from app.modassembly.database.sql.get_sql_session import Base, engine\n"
        )
        main_content += "Base.metadata.create_all(engine)\n"

    for component in architecture:
        if component.design.key == "app.main":
            assert len(component.files) == 1
            component.files[0].content = main_content
    with open(f"{REPOS}/{app_name}/app/main.py", "w") as f:
        f.write(main_content)


def update_architecture_dependencies(architecture: List[ImplementedComponent]) -> None:
    for component in architecture:
        if isinstance(component.design.root, Infrastructure) or isinstance(
            component.design.root, Service
        ):
            continue
        dependencies = set()
        for file in component.files:
            imports = extract_imports(file.content)
            for import_ in imports:
                if not import_.startswith("app."):
                    continue
                file_parts = import_.split(".")
                for file_path in ["/".join(file_parts[:-1]), "/".join(file_parts)]:
                    file_path = f"{file_path}.py"
                    for target_component in architecture:
                        if (
                            component.design.key != target_component.design.key
                            and not isinstance(
                                target_component.design.root, Infrastructure
                            )
                            and not isinstance(target_component.design.root, Service)
                            and file_path in [f.path for f in target_component.files]
                        ):
                            dependencies.add(target_component.design.key)
        component.design.root.dependencies = list(dependencies)


class Model(BaseModel):
    name: str
    module: str


def get_model_modules(app_name: str, ignore: List[str]) -> List[Model]:
    modules = []
    app_path = pathlib.Path(f"{REPOS}/{app_name}/app")
    for file_path in app_path.rglob("*.py"):
        if file_path.is_file():
            with open(file_path, "r") as f:
                code = f.read()
            models = extract_sqlalchemy_models(code)
            for model in models:
                if model in ignore:
                    continue
                module = file_path.relative_to(f"{REPOS}/{app_name}")
                module = str(module).replace("/", ".").replace(".py", "")
                modules.append(Model(name=model, module=module))
    return modules


class ModelImplementationError(Exception):
    pass


def create_tables(repo_name: str, code: str) -> None:
    models = extract_sqlalchemy_models(code)
    model_modules = get_model_modules(repo_name, models)
    imports = "\n".join([f"from {m.module} import {m.name}" for m in model_modules])
    test_code = f"""
import sys
sys.path.insert(0, "{REPOS}/{repo_name}")
from sqlalchemy import create_engine
from app.modassembly.database.sql.get_sql_session import Base

# Configure Base before defining models
Base.metadata.clear()

{imports}

{code}

test_engine = create_engine(f"sqlite:///{REPOS}/{repo_name}/test.db")
model_classes = [{', '.join(models)}]
for model_class in model_classes:
    model_class.__table__.drop(bind=test_engine, checkfirst=True)
    model_class.__table__.create(bind=test_engine)
"""
    venv_python = os.path.join(REPOS, repo_name, "venv", "bin", "python3")
    process = subprocess.run(
        [venv_python, "-c", test_code], capture_output=True, text=True
    )
    if process.returncode != 0:
        raise ModelImplementationError(f"{process.stdout}\n{process.stderr}")


class MypyError(Exception):
    pass


def run_mypy(app_name: str, file_paths: List[str]) -> None:
    full_paths = [f"{REPOS}/{app_name}/{path}" for path in file_paths]

    venv_python = os.path.join(REPOS, app_name, "venv", "bin", "python3")
    process = subprocess.run(
        [
            venv_python,
            "-m",
            "mypy",
            *full_paths,
            "--no-incremental",
            "--cache-dir=/dev/null",
            "--sqlite-cache",
            "--python-version=3.13",
            "--disable-error-code=call-overload",
            "--disable-error-code=import-untyped",
            "--follow-imports=skip",
        ],
        capture_output=True,
        text=True,
    )
    print(process.stdout)
    print(process.stderr)
    if process.returncode != 0:
        raise MypyError(f"{process.stdout}\n{process.stderr}")
