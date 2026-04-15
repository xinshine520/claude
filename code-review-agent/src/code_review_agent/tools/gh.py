"""GitHub CLI command tool for Code Review Agent."""

import subprocess
import json
from typing import Any


async def run_gh_command(args: list[str]) -> dict[str, Any]:
    """
    Execute gh command.

    Args:
        args: GH command arguments (e.g., ["pr", "diff"])

    Returns:
        dict with stdout, stderr, exit_code
    """
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            cwd=None,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": "gh command not found. Please install GitHub CLI: https://cli.github.com",
            "exit_code": 127,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
        }


async def get_current_pr() -> dict | None:
    """Get current branch's PR info."""
    result = await run_gh_command(["pr", "view", "--json", "number,title,base,head"])
    if result["exit_code"] == 0:
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return None
    return None


async def get_pr_info(pr_number: str) -> dict | None:
    """Get PR info by number."""
    result = await run_gh_command(["pr", "view", pr_number, "--json", "number,title,base,head,url"])
    if result["exit_code"] == 0:
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return None
    return None


async def get_pr_diff(pr: str | None = None) -> str:
    """Get PR diff."""
    if pr:
        result = await run_gh_command(["pr", "diff", pr])
    else:
        result = await run_gh_command(["pr", "diff"])
    return result["stdout"]


async def list_prs(state: str = "open") -> list[dict]:
    """List PRs."""
    result = await run_gh_command(["pr", "list", "--state", state, "--json", "number,title,headRefName,baseRefName"])
    if result["exit_code"] == 0:
        try:
            return json.loads(result["stdout"])
        except json.JSONDecodeError:
            return []
    return []


async def get_pr_comments(pr_number: str) -> list[dict]:
    """Get PR review comments."""
    result = await run_gh_command(["pr", "view", pr_number, "--json", "comments"])
    if result["exit_code"] == 0:
        try:
            data = json.loads(result["stdout"])
            return data.get("comments", [])
        except json.JSONDecodeError:
            return []
    return []
