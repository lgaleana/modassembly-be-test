import ast
import importlib
import importlib.util
import sys
from typing import List


def check_imports(code: str, app_name: str) -> None:
    site_packages = f"db/repos/{app_name}/venv/lib/python3.13/site-packages"
    sys.path.append(site_packages)
    site_packages = f"db/repos/{app_name}/venv/lib/python3.11/site-packages"
    sys.path.append(site_packages)

    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                if importlib.util.find_spec(name.name) is None:
                    raise ImportError(f"Module {name.name} not found")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                if importlib.util.find_spec(node.module) is None:
                    raise ImportError(f"Module {node.module} not found")
                # Note: We can't easily verify submodule imports without loading the module


class RouterNotFoundError(Exception):
    pass


def extract_router_name(code: str) -> str:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Name):
                        if node.value.func.id == "APIRouter":
                            return node.targets[0].id
    raise RouterNotFoundError("No APIRouter found")


def extract_sqlalchemy_models(code: str) -> List[str]:
    models = []
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "Base":
                    models.append(node.name)
                    break
    return models
