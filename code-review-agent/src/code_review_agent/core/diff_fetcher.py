"""Diff Fetcher - 获取代码差异."""

import re
from ..types import ReviewScope, DiffMetadata
from ..tools import git as git_tools
from ..tools import gh as gh_tools


class DiffFetcher:
    """获取代码差异"""

    async def get_diff(self, scope: ReviewScope) -> tuple[str, DiffMetadata]:
        """
        根据审查范围获取差异

        Args:
            scope: ReviewScope 对象

        Returns:
            (diff, metadata) 元组
        """
        if scope.type == "pr":
            return await self._get_pr_diff(scope.value)

        if scope.type == "commit":
            return await self._get_commit_diff(scope.value)

        if scope.type == "branch":
            return await self._get_branch_diff(scope.value, scope.base_branch)

        if scope.type == "staged":
            return await self._get_staged_diff()

        if scope.type == "unstaged":
            return await self._get_unstaged_diff()

        return "", DiffMetadata()

    async def _get_pr_diff(self, pr: str | None) -> tuple[str, DiffMetadata]:
        """获取 PR diff"""
        diff = await gh_tools.get_pr_diff(pr)
        metadata = self._parse_diff_metadata(diff)
        return diff, metadata

    async def _get_commit_diff(self, commit: str) -> tuple[str, DiffMetadata]:
        """获取 commit diff"""
        diff = await git_tools.get_commit_diff(commit)
        metadata = self._parse_diff_metadata(diff)
        return diff, metadata

    async def _get_branch_diff(self, branch: str | None, base: str | None) -> tuple[str, DiffMetadata]:
        """获取 branch diff"""
        if not base:
            base = "main"
        diff = await git_tools.get_diff(base, branch or "HEAD")
        metadata = self._parse_diff_metadata(diff)
        return diff, metadata

    async def _get_staged_diff(self) -> tuple[str, DiffMetadata]:
        """获取 staged diff"""
        diff = await git_tools.get_staged_diff()
        metadata = self._parse_diff_metadata(diff)
        return diff, metadata

    async def _get_unstaged_diff(self) -> tuple[str, DiffMetadata]:
        """获取 unstaged diff"""
        diff = await git_tools.get_unstaged_diff()
        metadata = self._parse_diff_metadata(diff)
        return diff, metadata

    def _parse_diff_metadata(self, diff: str) -> DiffMetadata:
        """解析 diff 获取元数据"""
        metadata = DiffMetadata()

        # 统计文件变更数
        diff_lines = diff.split("\n")
        for line in diff_lines:
            if line.startswith("diff --git"):
                metadata.files_changed += 1

        # 统计行数变更
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                metadata.lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                metadata.lines_removed += 1

        return metadata

    def extract_files_from_diff(self, diff: str) -> list[str]:
        """从 diff 中提取文件列表"""
        files = []
        for line in diff.split("\n"):
            if line.startswith("diff --git"):
                # 提取文件名 a/src/file.py b/src/file.py
                parts = line.split()
                if len(parts) >= 4:
                    # 去掉 a/ 或 b/
                    file_path = parts[2][2:] if parts[2].startswith("a/") else parts[2]
                    files.append(file_path)
        return list(set(files))
