import ast

from utils.files import File


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
