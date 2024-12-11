import json
import re

from dotenv import load_dotenv
import matplotlib.pyplot as plt
import networkx as nx

load_dotenv()

from ai import llm
from state import Conversation
from utils.io import print_system


def visualize_graph(G: nx.DiGraph, *, figsize=(12, 12), k=0.15, iterations=20):
    pos = nx.spring_layout(G, k=k, iterations=iterations)
    plt.figure(figsize=figsize)

    nx.draw_networkx_nodes(G, pos, node_size=500, node_color="lightblue")
    nx.draw_networkx_edges(G, pos, arrows=True)

    labels = {node: node for node in G.nodes()}
    nx.draw_networkx_labels(G, pos, labels, font_size=8)

    plt.axis("off")
    plt.show()


if __name__ == "__main__":
    conversation = Conversation()
    conversation.add_user(
        """Design the architecture (no code) of a python module that scrapes the text of any website. Use a modular and composable design pattern. Prefer functions over classes. To express the control flow, use an adjacency list.

Use the following json format:

```json
{
  "component1": {
    "description": ...
    "dependencies": [...]
  },
  "component2": ...
}```"""
    )
    response = llm.stream_text(conversation)

    json_match = re.search(r"```json\n(.*?)```", response, re.DOTALL)
    if json_match:
        adj_json = json_match.group(1)
        print_system(adj_json)

        G = nx.DiGraph()
        components = json.loads(adj_json)
        for component, details in components.items():
            G.add_node(component)
            for dependency in details["dependencies"]:
                G.add_edge(component, dependency)
        visualize_graph(G)
