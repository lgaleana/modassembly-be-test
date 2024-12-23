import ast
from importlib.util import find_spec

from utils.files import File


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


def extract_router_name(file: File) -> str:
    tree = ast.parse(file.content)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Name):
                        if node.value.func.id in ["APIRouter", "FastAPI"]:
                            return node.targets[0].id
    raise ValueError("No router found")
