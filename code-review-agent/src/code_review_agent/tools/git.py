"""Git command tool for Code Review Agent."""

import subprocess
import io
import sys
from typing import Any
from ..types import GitCommandResult


async def run_git_command(args: list[str]) -> dict[str, Any]:
    """
    Execute git command.

    Args:
        args: Git command arguments (e.g., ["diff", "main..HEAD"])

    Returns:
        dict with stdout, stderr, exit_code
    """
    try:
        # Use universal_newlines with errors='replace' to handle encoding issues
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            errors="replace",  # Replace invalid chars instead of crashing
            cwd=None,  # Use current working directory
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": "git command not found. Please ensure git is installed.",
            "exit_code": 127,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1,
        }


async def get_current_branch() -> str | None:
    """Get current branch name."""
    result = await run_git_command(["branch", "--show-current"])
    if result["exit_code"] == 0:
        return result["stdout"].strip()
    return None


async def get_diff(base: str, head: str = "HEAD") -> str:
    """
    Get diff between two refs.

    Args:
        base: Base branch/tag/commit
        head: Head branch/tag/commit (default: HEAD)

    Returns:
        Diff output
    """
    result = await run_git_command(["diff", f"{base}..{head}"])
    return result["stdout"]


async def get_staged_diff() -> str:
    """Get staged changes diff."""
    result = await run_git_command(["diff", "--cached"])
    return result["stdout"]


async def get_unstaged_diff() -> str:
    """Get unstaged changes diff."""
    result = await run_git_command(["diff"])
    return result["stdout"]


async def get_commit_diff(commit: str) -> str:
    """Get diff for a specific commit."""
    result = await run_git_command(["show", commit, "--format="])
    return result["stdout"]


async def get_file_history(file_path: str, limit: int = 10) -> str:
    """Get file commit history."""
    result = await run_git_command(["log", f"--oneline", f"-n{limit}", "--", file_path])
    return result["stdout"]


async def get_file_blame(file_path: str) -> str:
    """Get blame info for a file."""
    result = await run_git_command(["blame", file_path])
    return result["stdout"]


async def get_upstream_branch() -> str | None:
    """Get upstream branch for current branch."""
    result = await run_git_command([
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}"
    ])
    if result["exit_code"] == 0:
        # origin/main -> main
        return result["stdout"].strip().split("/")[-1]
    return None


async def is_ancestor(commit: str, ancestor_of: str) -> bool:
    """Check if commit is ancestor of another."""
    result = await run_git_command(["merge-base", "--is-ancestor", ancestor_of, commit])
    return result["exit_code"] == 0
