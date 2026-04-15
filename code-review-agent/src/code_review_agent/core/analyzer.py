"""Review Analyzer - 分析代码问题."""

import re
from ..types import ReviewScope, Issue, ReviewReport, DiffMetadata


class ReviewAnalyzer:
    """分析代码问题"""

    # Bug 模式
    BUG_PATTERNS = [
        (r"if\s*\(\s*!?\w+\s*==\s*null", "可能的空指针检查", "major", "bug"),
        (r"if\s*\(\s*null\s*==\s*\w+", "Yoda 空指针检查（推荐）", "minor", "style"),
        (r"\.exec\(", "使用 exec 可能存在安全风险", "major", "security"),
        (r"eval\(", "使用 eval 可能存在安全风险", "critical", "security"),
        (r"catch\s*\([^)]*\)\s*{\s*}", "空 catch 块，异常被静默吞掉", "major", "bug"),
        (r"catch\s*\([^)]*\)\s*{\s*pass\s*;?\s*}", "使用 pass 忽略异常", "major", "bug"),
        (r"except\s*:\s*$", "裸 except，捕获所有异常", "major", "bug"),
        (r"for\s+.*in\s+range\(.*\):\s*\n\s*.*\.append\(", "使用列表推导式替代循环", "minor", "performance"),
        (r"==\s*True", "使用 'is' 替代 '== True'", "minor", "style"),
        (r"==\s*False", "使用 'is not' 替代 '== False'", "minor", "style"),
    ]

    # 安全模式
    SECURITY_PATTERNS = [
        (r"password\s*=", "硬编码密码", "major", "security"),
        (r"api[_-]?key\s*=", "硬编码 API Key", "critical", "security"),
        (r"secret\s*=", "硬编码密钥", "major", "security"),
        (r"token\s*=", "硬编码 Token", "major", "security"),
        (r"subprocess\.", "使用 subprocess 可能存在风险", "minor", "security"),
        (r"os\.system\(", "使用 os.system 可能存在风险", "major", "security"),
    ]

    # 代码结构模式
    STRUCTURE_PATTERNS = [
        (r"def\s+\w+\([^)]{100,}", "函数参数过多", "minor", "structure"),
        (r"class\s+\w+.*:\s*\n(?:(?!    ).)+\n(?:    .*\n){50,}", "类过长（>50 行）", "minor", "structure"),
        (r"def\s+\w+\([^)]{30,}\)", "函数参数过多", "minor", "structure"),
        (r"if\s+.*:\s*return.*\n.*else:", "不必要的 else 分支", "minor", "style"),
        (r"^\s{100,}", "行过长（>100 字符）", "minor", "style"),
    ]

    async def analyze(
        self,
        diff: str,
        file_contents: dict[str, dict],
        scope: ReviewScope,
        metadata: DiffMetadata | None = None,
    ) -> ReviewReport:
        """
        分析代码，生成审查报告

        Args:
            diff: Git diff
            file_contents: 文件内容字典
            scope: 审查范围
            metadata: Diff 元数据

        Returns:
            ReviewReport
        """
        issues = []

        # 对每个文件进行分析
        for file_path, file_data in file_contents.items():
            if file_data.get("error"):
                continue

            content = file_data.get("content", "")
            file_diff = self._extract_file_diff(diff, file_path)

            # 分析各类问题
            issues.extend(await self._analyze_bugs(file_path, file_diff, content))
            issues.extend(await self._analyze_security(file_path, file_diff, content))
            issues.extend(await self._analyze_structure(file_path, file_diff, content))
            issues.extend(await self._analyze_style(file_path, file_diff, content))

        # 生成总结
        summary = self._generate_summary(issues, metadata)

        return ReviewReport(
            scope=scope,
            issues=issues,
            summary=summary,
            metadata={
                "files_changed": metadata.files_changed if metadata else 0,
                "lines_added": metadata.lines_added if metadata else 0,
                "lines_removed": metadata.lines_removed if metadata else 0,
                "issues_found": len(issues),
            } if metadata else None,
        )

    async def _analyze_bugs(self, file_path: str, diff: str, full_content: str) -> list[Issue]:
        """分析潜在的 bug"""
        return self._find_pattern_issues(file_path, diff, self.BUG_PATTERNS)

    async def _analyze_security(self, file_path: str, diff: str, full_content: str) -> list[Issue]:
        """分析安全问题"""
        return self._find_pattern_issues(file_path, diff, self.SECURITY_PATTERNS)

    async def _analyze_structure(self, file_path: str, diff: str, full_content: str) -> list[Issue]:
        """分析代码结构问题"""
        return self._find_pattern_issues(file_path, diff, self.STRUCTURE_PATTERNS)

    async def _analyze_style(self, file_path: str, diff: str, full_content: str) -> list[Issue]:
        """分析代码风格问题"""
        issues = []

        # 检查新增的代码行
        diff_lines = diff.split("\n")
        for i, line in enumerate(diff_lines):
            if line.startswith("+") and not line.startswith("+++"):
                line_num = i + 1
                issues.extend(self._check_line_style(file_path, line, line_num))

        return issues

    def _find_pattern_issues(
        self,
        file_path: str,
        diff: str,
        patterns: list[tuple[str, str, str, str]],
    ) -> list[Issue]:
        """查找匹配模式的代码问题"""
        issues = []

        for pattern, description, severity, issue_type in patterns:
            matches = re.finditer(pattern, diff, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                # 计算行号
                line_num = diff[:match.start()].count("\n") + 1

                issues.append(Issue(
                    severity=severity,
                    type=issue_type,
                    file=file_path,
                    line=line_num,
                    description=description,
                ))

        return issues

    def _check_line_style(self, file_path: str, line: str, line_num: int) -> list[Issue]:
        """检查单行代码风格"""
        issues = []

        # 检查行尾空格
        if line.rstrip() != line:
            issues.append(Issue(
                severity="minor",
                type="style",
                file=file_path,
                line=line_num,
                description="行尾有多余空格",
            ))

        # 检查行长度（针对新增内容）
        if len(line) > 120:
            issues.append(Issue(
                severity="minor",
                type="style",
                file=file_path,
                line=line_num,
                description=f"行过长（{len(line)} 字符，建议 <120）",
            ))

        return issues

    def _extract_file_diff(self, full_diff: str, file_path: str) -> str:
        """从完整 diff 中提取特定文件的 diff"""
        lines = full_diff.split("\n")
        file_diff_lines = []
        in_target_file = False

        for line in lines:
            if line.startswith("diff --git"):
                # 检查是否是目标文件
                if f"/{file_path}" in line or line.endswith(f"/{file_path}") or line.endswith(file_path):
                    in_target_file = True
                else:
                    in_target_file = False

            if in_target_file:
                file_diff_lines.append(line)

        return "\n".join(file_diff_lines)

    def _generate_summary(self, issues: list[Issue], metadata: DiffMetadata | None) -> str:
        """生成审查总结"""
        if not issues:
            if metadata and metadata.files_changed > 0:
                return "代码审查通过，未发现明显问题。"
            return "没有发现代码变更。"

        # 按严重性统计
        critical = sum(1 for i in issues if i.severity == "critical")
        major = sum(1 for i in issues if i.severity == "major")
        minor = sum(1 for i in issues if i.severity == "minor")

        # 按类型统计
        by_type = {}
        for i in issues:
            by_type[i.type] = by_type.get(i.type, 0) + 1

        summary_parts = []
        if critical > 0:
            summary_parts.append(f"严重问题: {critical} 个")
        if major > 0:
            summary_parts.append(f"重要问题: {major} 个")
        if minor > 0:
            summary_parts.append(f"轻微问题: {minor} 个")

        summary = f"发现 {len(issues)} 个问题: {', '.join(summary_parts)}"

        if by_type:
            type_strs = [f"{t}: {c}" for t, c in by_type.items()]
            summary += f"\n类型分布: {', '.join(type_strs)}"

        return summary
