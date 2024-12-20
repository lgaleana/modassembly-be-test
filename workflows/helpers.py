import ast
import json
import os
import re
import subprocess
from importlib.util import find_spec
from typing import Any, Dict, List, Optional, Set, Tuple

import matplotlib.pyplot as plt
import networkx as nx
from pydantic import BaseModel

from utils.files import File
from utils.io import print_system
from utils.static_analysis import extract_router_name


REPOS = "db/repos"


class Component(BaseModel):
    type: str
    name: str
    purpose: str
    uses: List[str]
    pypi_packages: List[str]
    external_infrastructure: List[str]
    is_api: bool
    file: Optional[File] = None


def extract_from_pattern(response: str, *, pattern: str) -> str:
    match = re.search(pattern, response, re.DOTALL)
    if not match:
        raise ValueError("No match found in response")
    extracted = match.group(1)
    print_system(extracted)
    return extracted


def extract_json(response: str, *, pattern: str) -> Any:
    json_str = extract_from_pattern(response, pattern=pattern)
    return json.loads(json_str)


def visualize_graph(G: nx.DiGraph, *, figsize=(12, 12), k=0.15, iterations=20):
    pos = nx.spring_layout(G, k=k, iterations=iterations)
    plt.figure(figsize=figsize)

    nx.draw_networkx_nodes(G, pos, node_size=500, node_color="lightblue")
    nx.draw_networkx_edges(G, pos, arrows=True)

    labels = {node: node for node in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=8)

    plt.axis("off")
    plt.show()


def build_graph(architecture: List[Component]) -> nx.DiGraph:
    G = nx.DiGraph()
    for component in architecture:
        G.add_node(component.name)
        for dependency in component.uses:
            G.add_edge(component.name, dependency)
        for infra in component.external_infrastructure:
            G.add_edge(component.name, f"{component.name}:{infra}")
    return G


def group_nodes_by_dependencies(architecture: List[Component]) -> List[Set[str]]:
    # Cursor function

    component_map = {comp.name: comp.uses for comp in architecture}
    remaining_nodes = set(component_map.keys())
    levels = []

    while remaining_nodes:
        # Find nodes whose dependencies have all been processed
        current_level = {
            node
            for node in remaining_nodes
            if all(dep not in remaining_nodes for dep in component_map[node])
        }

        if not current_level:
            raise ValueError("Circular dependency detected")

        levels.append(current_level)
        remaining_nodes -= current_level

    return levels


def control_flow_str(control_flow: Dict[str, Dict[str, List[str]]]) -> str:
    str_ = ""
    for component, details in control_flow.items():
        str_ += f"{component}:\n    Calls: {', '.join(details['calls'])}\n"
    return str_


def check_imports(code: str) -> None:
    tree = ast.parse(code)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imports.append(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    for import_path in imports:
        if import_path.startswith("repo."):
            spec = find_spec(import_path)
            if spec is None:
                raise ImportError(f"Import '{import_path}' not found")


def load_helpers(architecture: Dict[str, Component]) -> Tuple[File, File]:
    has_db = False
    for component in architecture.values():
        for external in component.external_infrastructure:
            if external == "database":
                has_db = True

    if has_db:
        with open(f"{REPOS}/_template/helpers/db.py", "r") as f:
            db_helper = File(path=f"app/helpers/db.py", content=f.read())

    with open(f"{REPOS}/_template/main.py", "r") as f:
        main = File(path=f"app/main.py", content=f.read())

    return db_helper, main


def save_files(
    app_name: str, db_helper: File, main: File, architecture: Dict[str, Component]
) -> None:
    main.content += "\n"
    for component in architecture.values():
        if component.is_api:
            assert component.file
            module = component.file.path.replace(".py", "").replace("/", ".")
            router_name = extract_router_name(component.file)
            main.content += f"from {module} import {router_name}\n"
            main.content += f"app.include_router({router_name})\n"

    for helper in [db_helper, main]:
        helper_path = f"{REPOS}/{app_name}/{helper.path}"
        os.makedirs(os.path.dirname(helper_path), exist_ok=True)
        with open(helper_path, "w") as f:
            f.write(helper.content)

    for file in ["deploy.sh", "Dockerfile", "requirements.txt"]:
        with open(f"{REPOS}/_template/{file}", "r") as f1, open(
            f"{REPOS}/{app_name}/{file}", "w"
        ) as f2:
            f2.write(f1.read())


def execute_deploy(app_name: str) -> str:
    os.chdir(f"{REPOS}/{app_name}")
    subprocess.run(["chmod", "+x", "deploy.sh"], check=True)
    output = subprocess.run(
        ["./deploy.sh", app_name], check=True, capture_output=True, text=True
    )
    return output.stdout.splitlines()[-1]
