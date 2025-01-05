import ast
from typing import List


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


def extract_imports(code: str) -> List[str]:
    imports = []
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imports.append(name.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for name in node.names:
                imports.append(f"{module}.{name.name}" if module else name.name)
    return imports
