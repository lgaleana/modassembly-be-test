import os
import requests
import subprocess
from typing import Any, Dict, List

from utils.files import REPOS


TOKEN = os.environ["GITHUB_TOKEN"]
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
OWNER = "lgaleana"
ORG = "Modular-Asembly"


def create_github_repository(repo: str) -> str:
    response = requests.post(
        f"https://api.github.com/orgs/{ORG}/repos",
        headers=HEADERS,
        json={"name": repo},
    )
    response.raise_for_status()
    return f"https://github.com/{ORG}/{repo}"


def protect_repository(repo: str) -> Dict[str, Any]:
    response = requests.put(
        f"https://api.github.com/repos/{ORG}/{repo}/branches/main/protection",
        headers=HEADERS,
        json={
            "required_status_checks": None,
            "enforce_admins": False,
            "required_pull_request_reviews": {
                "dismissal_restrictions": {},
                "dismiss_stale_reviews": True,
                "require_code_owner_reviews": False,
                "required_approving_review_count": 1,
                "bypass_pull_request_allowances": {"users": [OWNER]},
            },
            "restrictions": {"users": [OWNER], "teams": [], "apps": []},
            "required_linear_history": True,
            "allow_force_pushes": False,
            "allow_deletions": False,
        },
    )
    response.raise_for_status()
    return response.json()


def repository_exists(repo: str) -> bool:
    try:
        response = requests.get(
            f"https://api.github.com/repos/{ORG}/{repo}", headers=HEADERS
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def execute_git_commands(commands: List[List[str]], *, app: str) -> None:
    for command in commands:
        try:
            subprocess.run(command, check=True, cwd=f"{REPOS}/{app}")
        except subprocess.CalledProcessError as e:
            revert_changes(app)
            raise e


def revert_changes(app: str) -> None:
    execute_git_commands(
        [
            ["git", "reset", "HEAD", "."],
            ["git", "clean", "-fd"],
            ["git", "checkout", "."],
        ],
        app=app,
    )
