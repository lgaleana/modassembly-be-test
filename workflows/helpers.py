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
    BaseComponent,
    Function,
    ImplementedComponent,
    SQLAlchemyModel,
)
from utils.io import print_system
from utils.static_analysis import extract_router_name, extract_sqlalchemy_models


REPOS = "db/repos"


def extract_from_pattern(response: str, *, pattern: str) -> List[str]:
    matches = re.findall(pattern, response, re.DOTALL)
    if not matches:
        raise ValueError("No matches found in response")
    for match in matches:
        print_system(match)
    return matches


def extract_json(response: str, *, pattern: str) -> List[Any]:
    json_str = extract_from_pattern(response, pattern=pattern)
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


def build_graph(architecture: List[BaseComponent]) -> nx.DiGraph:
    G = nx.DiGraph()
    for component in architecture:
        G.add_node(component.name)
        for dependency in component.uses:
            G.add_edge(component.name, dependency)
    return G


def install_requirements(pypi_packages: Set[str], app_name: str) -> None:
    venv_path = f"db/repos/{app_name}/venv"
    os.makedirs(venv_path, exist_ok=True)
    venv.create(venv_path, with_pip=True)
    venv_python = os.path.join(venv_path, "bin", "python3")
    print_system("Installing requirements...")
    output = subprocess.run(
        [venv_python, "-m", "pip", "install", *pypi_packages],
        check=False,
        capture_output=True,
        text=True,
    )
    print_system(output.stdout)
    print_system(output.stderr)
    if output.returncode != 0:
        raise Exception(f"{output.stdout}\n{output.stderr}")


def group_nodes_by_dependencies(
    architecture: List[ImplementedComponent],
) -> List[Set[str]]:
    levels = []
    dependencies = {}
    for component in architecture:
        if isinstance(component.base.root, SQLAlchemyModel):
            dependencies[component.base.root.key] = component.base.root.associations
        elif isinstance(component.base.root, Function):
            dependencies[component.base.root.key] = component.base.root.uses

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
    architecture: Dict[str, ImplementedComponent],
    external_infrastructure: List[str],
) -> None:
    with open(f"{REPOS}/{app_name}/app/main.py", "r") as f:
        main_content = f.read()
    main_content += "\n"
    for component in architecture.values():
        if (
            isinstance(component.base.root, Function)
            and component.base.root.is_endpoint
        ):
            assert component.file
            module = component.file.path.replace(".py", "").replace("/", ".")
            router_name = extract_router_name(component.file.content)
            main_content += f"from {module} import {router_name}\n"
            main_content += f"app.include_router({router_name})\n"
    if "database" in external_infrastructure:
        main_content += "\nfrom app.helpers.db import Base, engine\n"
        main_content += "Base.metadata.create_all(engine)\n"
    with open(f"{REPOS}/{app_name}/app/main.py", "w") as f:
        f.write(main_content)


def execute_deploy(app_name: str) -> str:
    original_dir = os.getcwd()
    try:
        os.chdir(f"{REPOS}/{app_name}")
        subprocess.run(["chmod", "+x", "deploy.sh"], check=True)
        output = subprocess.run(
            ["./deploy.sh", app_name], check=True, capture_output=True, text=True
        )
        print_system(output.stdout)
        print_system(output.stderr)
        return output.stdout.splitlines()[-1]
    finally:
        os.chdir(original_dir)


def create_tables(app_name: str, namespace: str, code: str) -> None:
    models = extract_sqlalchemy_models(code)
    for model in models:
        module_path = f"db.repos.{app_name}.app.{namespace}.{model}"
        models_module = importlib.import_module(module_path)
        model_class = getattr(models_module, model)
        db_module = importlib.import_module(f"db.repos.{app_name}.app.helpers.db")
        engine = getattr(db_module, "engine")
        try:
            model_class.__table__.drop(bind=engine)
        except Exception:
            pass
        model_class.__table__.create(bind=engine)


class MypyError(Exception):
    pass


def run_mypy(file_path: str) -> None:
    stdout, stderr, exit_code = api.run(
        [
            file_path,
            "--disable-error-code=import-untyped",
        ]
    )
    print_system(stdout)
    print_system(stderr)
    if exit_code != 0:
        raise MypyError(f"{exit_code}\n{stdout}")
