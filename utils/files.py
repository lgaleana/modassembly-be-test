import os
from pydantic import BaseModel


REPOS = os.path.expanduser("~/repos")


class File(BaseModel):
    path: str
    content: str


def create_folders_if_not_exist(app_name: str, path: str) -> None:
    packages = path.split("/")
    current_path = f"{REPOS}/{app_name}"
    for package in packages:
        current_path = os.path.join(current_path, package)
        if not os.path.exists(current_path):
            os.mkdir(current_path)
        init_file = os.path.join(current_path, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w") as f:
                f.write("")
