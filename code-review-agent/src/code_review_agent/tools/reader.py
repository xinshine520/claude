"""File reader tool for Code Review Agent."""

import os
from typing import Any


async def read_file(file_path: str) -> dict[str, Any]:
    """
    Read file content.

    Args:
        file_path: Path to file (relative or absolute)

    Returns:
        dict with content, lines, error
    """
    try:
        # Resolve relative paths from current working directory
        if not os.path.isabs(file_path):
            file_path = os.path.join(os.getcwd(), file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = len(content.splitlines())

        return {
            "content": content,
            "lines": lines,
            "error": None,
        }
    except FileNotFoundError:
        return {
            "content": "",
            "lines": 0,
            "error": f"File not found: {file_path}",
        }
    except PermissionError:
        return {
            "content": "",
            "lines": 0,
            "error": f"Permission denied: {file_path}",
        }
    except Exception as e:
        return {
            "content": "",
            "lines": 0,
            "error": str(e),
        }


async def read_multiple_files(file_paths: list[str]) -> dict[str, dict[str, Any]]:
    """
    Read multiple files.

    Args:
        file_paths: List of file paths

    Returns:
        dict mapping file path to read result
    """
    results = {}
    for path in file_paths:
        results[path] = await read_file(path)
    return results
