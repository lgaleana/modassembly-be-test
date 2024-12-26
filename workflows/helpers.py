import json
import os
import re
import shutil
import subprocess
import venv
from tempfile import mkdtemp
from typing import Any, Dict, List, Literal, Optional, Set

import matplotlib.pyplot as plt
import networkx as nx
from pydantic import BaseModel, Field

from utils.files import File
from utils.io import print_system


REPOS = "db/repos"


class RawComponent(BaseModel):
    type: Literal["struct", "function"] = Field(description="struct or function")
    name: str = Field(description="The name of the struct or function")
    purpose: str = Field(description="The purpose of the struct or function")
    uses: List[str] = Field(
        description="The structs or functions that this component uses internally"
    )
    pypi_packages: List[str] = Field(
        description="The pypi packages that the component will need"
    )
    is_endpoint: bool = Field(description="Whether this is a FastAPI endpoint")


class Component(RawComponent):
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


def build_graph(architecture: List[RawComponent]) -> nx.DiGraph:
    G = nx.DiGraph()
    for component in architecture:
        G.add_node(component.name)
        for dependency in component.uses:
            G.add_edge(component.name, dependency)
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


def install_requirements(pypi_packages: Set[str], app_name: str) -> None:
    venv_path = f"db/repos/{app_name}/venv"
    os.makedirs(venv_path, exist_ok=True)
    venv.create(venv_path, with_pip=True)
    venv_python = os.path.join(venv_path, "bin", "python3")
    print_system("Installing requirements...")
    output = subprocess.run(
        [venv_python, "-m", "pip", "install", *pypi_packages],
        check=True,
        capture_output=True,
        text=True,
    )
    print_system(output.stdout)
    print_system(output.stderr)
    if output.returncode != 0:
        raise Exception(f"{output.stdout}\n{output.stderr}")
