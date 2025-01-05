import json
import importlib
import os
import re
import subprocess
import venv
from mypy import api
from typing import Any, Dict, List, Set

import matplotlib.pyplot as plt
import networkx as nx

from utils.architecture import (
    Function,
    ImplementedComponent,
    create_initial_config,
)
from utils.github import (
    create_github_repository,
    execute_git_commands,
    protect_repository,
    repository_exists,
)
from utils.io import print_system
from utils.state import Conversation
from utils.static_analysis import (
    extract_imports,
    extract_router_name,
    extract_sqlalchemy_models,
)


REPOS = os.path.expanduser("~/repos")


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
    return [json.loads(json_str) for json_str in json_str]


def visualize_graph(G: nx.DiGraph, *, figsize=(12, 12), k=0.15, iterations=20):
    pos = nx.spring_layout(G, k=k, iterations=iterations)
    plt.figure(figsize=figsize)

    nx.draw_networkx_nodes(G, pos, node_size=500, node_color="lightblue")
    nx.draw_networkx_edges(G, pos, arrows=True)

    labels = {node: node for node in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=8)

    plt.axis("off")
    plt.show()


def build_graph(architecture: List[ImplementedComponent]) -> nx.DiGraph:
    G = nx.DiGraph()
    for component in architecture:
        G.add_node(component.design.key)
        for dependency in component.design.root.dependencies:
            G.add_edge(component.design.key, dependency)
    return G


def create_app(app_name: str, external_infrastructure: List[str]) -> Dict[str, Any]:
    app_name = app_name.replace(" ", "-")
    if repository_exists(app_name):
        raise ValueError(f"Repository {app_name} already exists")
    os.mkdir(f"{REPOS}/{app_name}")
    Conversation().persist(app_name=app_name)
    with open(f"{REPOS}/fastapi-template/.gitignore", "r") as f1, open(
        f"{REPOS}/{app_name}/.gitignore", "w"
    ) as f2:
        content = f1.read()
        content = f"{content}\nDockerfile\ndeploy.sh\n"
        f2.write(content)
    print_system("Initializing git and github...")
    github_url = create_github_repository(app_name)
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
                f"git@github.com:Modular-Asembly/{app_name}.git",
            ],
            ["git", "push", "-u", "origin", "main"],
        ],
        app=app_name,
    )
    protect_repository(app_name)
    print_system("Success")
    config = create_initial_config(app_name, external_infrastructure, github_url)
    return config


class InstallRequirementsError(Exception):
    pass


def install_requirements(
    app_name: str,
    architecture: List[ImplementedComponent],
) -> None:
    pypi_packages = set()
    for component in architecture:
        pypi_packages.update(component.design.root.pypi_packages)
    requirements_path = f"{REPOS}/{app_name}/requirements.txt"
    with open(requirements_path, "w") as f:
        f.write("\n".join(pypi_packages))

    venv_path = f"{REPOS}/{app_name}/venv"
    os.makedirs(venv_path, exist_ok=True)
    venv.create(venv_path, with_pip=True)
    venv_python = os.path.join(venv_path, "bin", "python3")
    print_system("Installing requirements...")
    output = subprocess.run(
        [venv_python, "-m", "pip", "install", "-r", requirements_path],
        check=False,
        capture_output=True,
        text=True,
    )
    print_system(output.stdout)
    print_system(output.stderr)
    if output.returncode != 0:
        raise InstallRequirementsError(f"{output.stdout}\n{output.stderr}")


def create_folders_if_not_exist(app_name: str, namespace: str) -> None:
    packages = namespace.split(".")
    current_path = f"{REPOS}/{app_name}"
    for package in packages:
        current_path = os.path.join(current_path, package)
        if not os.path.exists(current_path):
            os.mkdir(current_path)
        init_file = os.path.join(current_path, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w") as f:
                f.write("")


def group_nodes_by_dependencies(
    architecture: List[ImplementedComponent],
) -> List[Set[str]]:
    levels = []
    dependencies = {}
    for component in architecture:
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
    external_infrastructure,
) -> None:
    with open(f"{REPOS}/{app_name}/app/main.py", "r") as f:
        main_content = f.read()
    main_content += "\n"
    for component in architecture:
        if (
            isinstance(component.design.root, Function)
            and component.design.root.is_endpoint
        ):
            assert component.file
            module = component.file.path.replace(".py", "").replace("/", ".")
            router_name = extract_router_name(component.file.content)
            main_content += f"from {module} import {router_name}\n"
            main_content += f"app.include_router({router_name})\n"
    if "sql" in external_infrastructure:
        main_content += "\n# Database\n"
        main_content += (
            "\nfrom app.modassembly.database.sql.get_sql_session import Base, engine\n"
        )
        main_content += "Base.metadata.create_all(engine)\n"
    with open(f"{REPOS}/{app_name}/app/main.py", "w") as f:
        f.write(main_content)


def update_architecture_dependencies(architecture: List[ImplementedComponent]) -> None:
    for component in architecture:
        assert component.file
        imports = extract_imports(component.file.content)
        dependencies = set()
        for import_ in imports:
            if not import_.startswith("app."):
                continue
            key = ".".join(import_.split(".")[1:-1])
            dependencies.add(key)
        component.design.root.dependencies = list(dependencies)


class ModelImplementationError(Exception):
    pass


def create_tables(app_name: str, namespace: str, code: str) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.schema import MetaData
    from sqlalchemy.ext.declarative import declarative_base

    metadata = MetaData()
    Base = declarative_base(metadata=metadata)
    models = extract_sqlalchemy_models(code)
    test_engine = create_engine(
        f"sqlite:///file:{app_name}?mode=memory&cache=shared&uri=true"
    )
    for model in models:
        module_path = f"app.{namespace}.{model}"
        models_module = importlib.import_module(module_path)
        model_class = getattr(models_module, model)
        if hasattr(model_class, "__table__"):
            model_class.__table__ = None
        model_class.metadata.clear()
        model_class.__bases__ = (Base,)
    try:
        metadata.create_all(bind=test_engine)
    except Exception as e:
        raise ModelImplementationError(f"Error creating tables: {e}")


class MypyError(Exception):
    pass


def run_mypy(file_path: str) -> None:
    stdout, stderr, exit_code = api.run(
        [
            file_path,
            "--disable-error-code=call-overload",
        ]
    )
    print_system(stdout)
    print_system(stderr)
    if exit_code != 0:
        raise MypyError(f"{stdout}\n{stderr}")
