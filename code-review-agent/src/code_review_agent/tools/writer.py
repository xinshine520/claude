"""File writer tool for Code Review Agent."""

import os
from typing import Any


async def write_file(file_path: str, content: str) -> dict[str, Any]:
    """
    Write content to file.

    Args:
        file_path: Path to file
        content: Content to write

    Returns:
        dict with success, error
    """
    try:
        # Ensure directory exists
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "success": True,
            "file_path": file_path,
            "error": None,
        }
    except PermissionError:
        return {
            "success": False,
            "file_path": file_path,
            "error": f"Permission denied: {file_path}",
        }
    except Exception as e:
        return {
            "success": False,
            "file_path": file_path,
            "error": str(e),
        }


async def append_file(file_path: str, content: str) -> dict[str, Any]:
    """
    Append content to file.

    Args:
        file_path: Path to file
        content: Content to append

    Returns:
        dict with success, error
    """
    try:
        # Ensure directory exists
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(content)

        return {
            "success": True,
            "file_path": file_path,
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "file_path": file_path,
            "error": str(e),
        }
