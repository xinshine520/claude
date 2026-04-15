"""Data types for Code Review Agent."""

from typing import Literal
from pydantic import BaseModel, Field


class ReviewScope(BaseModel):
    """审查范围"""
    type: Literal["pr", "commit", "branch", "staged", "unstaged"]
    value: str | None = None  # PR号、commit hash、branch名等
    base_branch: str | None = None  # 相对分支（用于 branch 类型）
    description: str | None = None  # 描述


class Issue(BaseModel):
    """代码问题"""
    severity: Literal["critical", "major", "minor"] = "minor"
    type: Literal["bug", "security", "structure", "performance", "style"] = "style"
    file: str
    line: int | None = None
    description: str
    suggestion: str | None = None  # 修复建议


class ReviewReport(BaseModel):
    """审查报告"""
    scope: ReviewScope
    issues: list[Issue] = Field(default_factory=list)
    summary: str = ""
    metadata: dict | None = None


class GitCommandResult(BaseModel):
    """Git 命令执行结果"""
    stdout: str
    stderr: str
    exit_code: int


class DiffMetadata(BaseModel):
    """Diff 元数据"""
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
