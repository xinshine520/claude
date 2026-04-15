"""Review Scope Detector - 确定审查范围."""

import re
from ..types import ReviewScope
from ..tools import git as git_tools
from ..tools import gh as gh_tools


class ReviewScopeDetector:
    """解析用户输入，确定审查范围"""

    COMMON_BRANCHES = ["main", "master", "develop", "dev"]

    async def detect(self, user_input: str) -> ReviewScope:
        """
        根据用户输入确定审查范围

        Args:
            user_input: 用户输入

        Returns:
            ReviewScope 对象
        """
        user_lower = user_input.lower()

        # PR 相关
        if any(kw in user_lower for kw in ["pr", "pull request", "pull"]):
            return await self._detect_pr_scope(user_input)

        # Commit 相关
        if any(kw in user_lower for kw in ["commit", "hash"]):
            return await self._detect_commit_scope(user_input)

        # Branch 相关
        if any(kw in user_lower for kw in ["branch", "分支", "my"]):
            return await self._detect_branch_scope(user_input)

        # Stage 相关 - 注意顺序：先检查 unstaged（因为包含 staged）
        if "unstaged" in user_lower:
            return ReviewScope(type="unstaged", description="Unstaged changes")
        if "staged" in user_lower:
            return ReviewScope(type="staged", description="Staged changes")

        # 默认：审查当前分支相对于 base 的变更
        return await self._detect_default_scope()

    async def _detect_pr_scope(self, user_input: str) -> ReviewScope:
        """检测 PR 相关范围"""
        # 检查是否指定了 PR 号
        pr_match = re.search(r"#?(\d+)", user_input)
        if pr_match:
            pr_number = pr_match.group(1)
            pr_info = await gh_tools.get_pr_info(pr_number)
            if pr_info:
                return ReviewScope(
                    type="pr",
                    value=pr_number,
                    description=f"PR #{pr_number}: {pr_info.get('title', '')}"
                )
            return ReviewScope(
                type="pr",
                value=pr_number,
                description=f"PR #{pr_number}"
            )

        # 尝试获取当前分支的 PR
        pr_info = await gh_tools.get_current_pr()
        if pr_info:
            return ReviewScope(
                type="pr",
                value=str(pr_info.get("number")),
                description=f"Current PR #{pr_info.get('number')}: {pr_info.get('title', '')}"
            )

        return ReviewScope(type="pr", description="Current branch PR")

    async def _detect_commit_scope(self, user_input: str) -> ReviewScope:
        """检测 Commit 相关范围"""
        # 尝试提取 commit hash
        # 支持各种格式: abc123, HEAD~, commit abc123, etc.
        commit_match = re.search(r"([a-f0-9]{4,40}|head~?\d*)", user_input.lower())
        if commit_match:
            commit = commit_match.group(1)
            if commit.startswith("head"):
                # Handle HEAD~n format
                return ReviewScope(type="commit", value=commit.upper(), description=f"Commit {commit}")

            # Short hash - use as is
            return ReviewScope(type="commit", value=commit, description=f"Commit {commit[:8]}")

        # 默认查看 HEAD
        return ReviewScope(type="commit", value="HEAD", description="Latest commit")

    async def _detect_branch_scope(self, user_input: str) -> ReviewScope:
        """检测 Branch 相关范围"""
        # 尝试提取分支名
        # 格式: review main, review branch xxx, etc.
        branch_match = re.search(r"(?:branch|分支|基于)\s+(\w+)", user_input.lower())
        if branch_match:
            branch = branch_match.group(1)
            current_branch = await git_tools.get_current_branch()
            return ReviewScope(
                type="branch",
                value=current_branch,
                base_branch=branch,
                description=f"{current_branch} vs {branch}"
            )

        # 默认使用当前分支
        current_branch = await git_tools.get_current_branch()
        base_branch = await self._detect_base_branch()
        return ReviewScope(
            type="branch",
            value=current_branch,
            base_branch=base_branch,
            description=f"{current_branch} vs {base_branch}"
        )

    async def _detect_default_scope(self) -> ReviewScope:
        """检测默认范围"""
        current_branch = await git_tools.get_current_branch()
        base_branch = await self._detect_base_branch()
        return ReviewScope(
            type="branch",
            value=current_branch,
            base_branch=base_branch,
            description=f"{current_branch} vs {base_branch}"
        )

    async def _detect_base_branch(self) -> str:
        """智能检测 base branch"""
        # 1. 尝试获取 upstream
        upstream = await git_tools.get_upstream_branch()
        if upstream:
            return upstream

        # 2. 尝试 common base branches
        for branch in self.COMMON_BRANCHES:
            is_ancestor = await git_tools.is_ancestor(branch, "HEAD")
            if is_ancestor:
                return branch

        return "main"
