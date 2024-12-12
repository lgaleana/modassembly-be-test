import json
import re
from typing import Any, Dict, List, Set

import matplotlib.pyplot as plt
import networkx as nx

from utils.io import print_system


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


def build_graph(architecture: Dict[str, Dict[str, List[str]]]) -> nx.DiGraph:
    G = nx.DiGraph()
    for module, details in architecture.items():
        G.add_node(module)
        for dependency in details["calls"]:
            G.add_edge(module, dependency)
    return G


def group_nodes_by_dependencies(
    architecture: Dict[str, Dict[str, List[str]]]
) -> List[Set[str]]:
    # Cursor function

    remaining_nodes = set(architecture.keys())
    levels = []

    while remaining_nodes:
        # Find nodes whose dependencies have all been processed
        current_level = {
            node
            for node in remaining_nodes
            if all(dep not in remaining_nodes for dep in architecture[node]["calls"])
        }

        if not current_level:
            raise ValueError("Circular dependency detected")

        levels.append(current_level)
        remaining_nodes -= current_level

    return levels
