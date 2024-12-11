import json
import re
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import networkx as nx

from utils.io import print_system


def extract_json(response: str, *, pattern: str) -> Dict[str, Any]:
    match = re.search(pattern, response, re.DOTALL)
    if not match:
        raise ValueError("No JSON found in response")
    json_str = match.group(1)
    print_system(json_str)
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


def build_graph(architecture: Dict[str, Dict[str, List[str]]]) -> None:
    G = nx.DiGraph()
    for component, details in architecture.items():
        G.add_node(component)
        for dependency in details["calls"]:
            G.add_edge(component, dependency)
    visualize_graph(G)
