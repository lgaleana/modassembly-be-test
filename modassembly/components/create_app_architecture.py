import json
from typing import Any, Dict
from workflows.helpers import Component


def create_app_architecture(app_name: str) -> Dict[str, Any]:
    with open(f"db/repos/example/config.json", "r") as f:
        return json.load(f)
