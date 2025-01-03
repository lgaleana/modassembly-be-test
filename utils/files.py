import os
from pydantic import BaseModel


REPOS = os.path.expanduser("~/repos")


class File(BaseModel):
    path: str
    content: str
