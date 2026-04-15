"""Code Review Agent - 主入口."""

import json
from simple_agent import SimpleAgent
from .types import ReviewScope, ReviewReport, Issue
from .core.scope_detector import ReviewScopeDetector
from .core.diff_fetcher import DiffFetcher
from .core.context_reader import ContextReader
from .core.analyzer import ReviewAnalyzer
from .tools import git as git_tools
from .tools import gh as gh_tools
from .tools import reader as reader_tools
from .tools import writer as writer_tools


# System prompt - 从文件加载
import os
SYSTEM_PROMPT = """You are a code review agent. Your job is to review code changes and provide actionable, high-quality feedback.

---

## Your Capabilities

You have access to these tools:
- **Read files**: Examine any file in the workspace to understand context
- **Write files**: Create or overwrite files (for saving review reports)
- **Git commands**: Run git commands to understand changes, history, and context
- **GH commands**: Run GitHub CLI commands for PR-related operations

You do NOT have access to:
- Edit tool (you can only write complete files)
- Shell commands beyond git and gh
- Network or external tools (except gh which uses GitHub API)

---

## Your Personality

Your default personality is **concise, direct, and friendly**. You communicate efficiently, keeping users informed without unnecessary detail. You prioritize actionable guidance.

**Be precise**: State assumptions, prerequisites, and next steps clearly. Don't guess or make up answers—investigate using your tools instead.

---

## Tool Usage Guide

### 1. Read File

Read the content of a file to understand context.

**Tool Name**: `read_file`
**Parameters**:
- `file_path`: Path to the file (relative to current directory or absolute)

### 2. Write File

Write content to a file (for review reports).

**Tool Name**: `write_file`
**Parameters**:
- `content`: Content to write
- `file_path`: Path to the file

### 3. Git Command

Run git commands to get diffs and understand changes.

**Tool Name**: `git_command`
**Parameters**:
- `args`: Git command arguments (as array)

### 4. GH Command

Run GitHub CLI commands for PR-related operations.

**Tool Name**: `gh_command`
**Parameters**:
- `args`: GH command arguments (as array)

---

## How to Determine What to Review

### 1. "Review current branch new code" / "Review my changes"
- Get current branch: git_command args=["branch", "--show-current"]
- Get diff against main/develop: git_command args=["diff", "main..HEAD"]

### 2. "Review commit xxx" / "Review last commit"
- git_command args=["show", "abc123"]

### 3. "Review PR" / "Review pull request"
- gh_command args=["pr", "view"]
- gh_command args=["pr", "diff"]

### 4. "Review staged changes"
- git_command args=["diff", "--cached"]

### 5. "Review all uncommitted changes"
- git_command args=["diff"]

---

## Gathering Context

**Diffs alone are never enough.** After getting the diff, read the full files being modified to understand complete context.

---

## What to Look For

### Bugs (Primary Focus)
- Logic errors, off-by-one mistakes, incorrect conditionals
- Missing or incorrect if-else guards, unreachable code paths
- Edge cases: null/empty/undefined inputs, error conditions
- Security issues: injection, auth bypass, data exposure
- Broken error handling

### Structure
- Does the code follow existing patterns and conventions?
- Excessive nesting that could be flattened

### Performance
- O(n²) on unbounded data
- N+1 queries

---

## Remember

- Focus on real problems, not hypotheticals
- When in doubt, investigate more before flagging
- Keep your tone collaborative and constructive
- Always read full files for context, not just diffs
"""


class CodeReviewAgent:
    """代码审查 Agent"""

    def __init__(self, model: str = "deepseek-chat"):
        """
        初始化 Code Review Agent

        Args:
            model: LLM 模型名称
        """
        self.agent = SimpleAgent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            use_deepseek=True,
        )
        self._register_tools()

        # 核心组件
        self.scope_detector = ReviewScopeDetector()
        self.diff_fetcher = DiffFetcher()
        self.context_reader = ContextReader()
        self.analyzer = ReviewAnalyzer()

    def _register_tools(self):
        """注册工具"""
        # 通用 Git 命令工具
        self.agent.add_tool(
            "git_command",
            git_tools.run_git_command,
            "Execute git command. Use this to run any git command like diff, status, log, show, etc.",
            {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Git command arguments (e.g., ['diff', 'main..HEAD'])"
                    },
                },
                "required": ["args"],
            },
        )

        # 通用 GH 命令工具
        self.agent.add_tool(
            "gh_command",
            gh_tools.run_gh_command,
            "Execute GitHub CLI command. Use this to run gh commands like pr view, pr diff, pr list, etc.",
            {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "GH command arguments (e.g., ['pr', 'diff', '123'])"
                    },
                },
                "required": ["args"],
            },
        )

        # 文件读写工具
        self.agent.add_tool(
            "read_file",
            reader_tools.read_file,
            "Read file content",
            {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "File path to read"},
                },
                "required": ["file_path"],
            },
        )

        self.agent.add_tool(
            "write_file",
            writer_tools.write_file,
            "Write content to file",
            {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["file_path", "content"],
            },
        )

    async def review(self, user_input: str) -> str:
        """
        执行代码审查

        Args:
            user_input: 用户输入

        Returns:
            审查结果
        """
        # 简单模式：直接使用 agent 进行审查
        result = await self.agent.run(user_input)
        return result

    async def review_with_report(self, user_input: str) -> ReviewReport:
        """
        执行代码审查并返回结构化报告

        Args:
            user_input: 用户输入

        Returns:
            结构化审查报告
        """
        # 1. 确定审查范围
        scope = await self.scope_detector.detect(user_input)

        # 2. 获取差异
        diff, metadata = await self.diff_fetcher.get_diff(scope)

        if not diff:
            return ReviewReport(
                scope=scope,
                issues=[],
                summary="没有发现代码变更",
                metadata={"files_changed": 0, "lines_added": 0, "lines_removed": 0},
            )

        # 3. 读取涉及的文件获取上下文
        file_contents = await self.context_reader.read_changed_files(diff)

        # 4. 分析代码问题
        report = await self.analyzer.analyze(diff, file_contents, scope, metadata)

        return report

    async def run_stream(self, user_input: str):
        """
        流式执行代码审查

        Args:
            user_input: 用户输入

        Yields:
            Agent 事件
        """
        async for event in self.agent.run_stream(user_input):
            yield event


# 便捷函数
async def quick_review(user_input: str) -> str:
    """
    快速代码审查

    Args:
        user_input: 用户输入

    Returns:
        审查结果
    """
    agent = CodeReviewAgent()
    return await agent.review(user_input)
