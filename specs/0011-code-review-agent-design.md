# Code Review Agent 设计规范

## 1. 核心概念

### 1.1 Agent 定义

Code Review Agent 是一个专注于代码审查的 Agent，能够：

1. 理解用户想要审查的代码范围（branch、commit、PR 等）
2. 使用 git/gh 命令获取代码差异
3. 读取完整文件以理解上下文
4. 分析代码中的问题（bug、结构、性能、安全）
5. 提供清晰、可执行的审查意见

```
┌─────────────────────────────────────────────────────────┐
│              Code Review Agent                           │
│                                                         │
│  用户输入 ──► 确定审查范围 ──► 获取 Diff ──► 读取文件   │
│       │                           │                     │
│       │                           ▼                     │
│       │                    分析代码问题 ──► 输出审查报告 │
│       │                           │                     │
│       └───────── 不明确时 ────────┘                     │
└─────────────────────────────────────────────────────────┘
```

### 1.2 设计目标

- **简洁高效**：快速确定审查范围，提供精准反馈
- **上下文感知**：不仅看 diff，还读取完整文件理解背景
- **实用导向**：关注真实问题，提供可执行的修复建议
- **多场景支持**：支持 branch、commit、PR、unstaged、staged 等各种场景

---

## 2. 工具定义

### 2.1 Read File（读取文件）

读取指定文件的内容，用于理解代码上下文。

```typescript
interface ReadFileInput {
  file_path: string  // 文件路径（相对或绝对）
}

interface ReadFileOutput {
  content: string    // 文件内容
  lines: number      // 总行数
}
```

**使用场景**：
- 读取 diff 中修改的文件，理解完整上下文
- 读取相关测试文件，理解预期行为
- 读取配置文件，了解项目规范

### 2.2 Write File（写入文件）

将审查报告写入指定文件。

```typescript
interface WriteFileInput {
  content: string   // 写入内容
  file_path: string // 文件路径
}
```

**使用场景**：
- 将审查报告保存到文件
- 创建 Markdown 格式的审查文档

### 2.3 Git Command（Git 命令）

执行 git 命令，获取代码差异和历史信息。

```typescript
interface GitCommandInput {
  args: string[]    // Git 命令参数数组
}

interface GitCommandOutput {
  stdout: string     // 命令输出
  stderr: string     // 错误输出
  exit_code: number // 退出码
}
```

**支持的命令模式**：

| 用户需求 | Git 命令 | 说明 |
|----------|----------|------|
| 审查当前分支相对 main 的变更 | `git diff main..HEAD` | Branch diff |
| 审查当前分支相对 develop 的变更 | `git diff develop..HEAD` | Branch diff |
| 审查未暂存的变更 | `git diff` | Unstaged diff |
| 审查已暂存的变更 | `git diff --cached` | Staged diff |
| 审查某个 commit | `git show <hash>` | Commit diff |
| 审查两个 commit 之间的变更 | `git diff <hash1>..<hash2>` | Range diff |
| 审查所有未推送的提交 | `git diff origin/branch..HEAD` | Unpushed diff |
| 查看文件历史 | `git log --oneline <file>` | File history |
| 查看谁改了某行 | `git blame <file>` | Blame info |
| 查看当前分支名 | `git branch --show-current` | Current branch |

### 2.4 GH Command（GitHub CLI 命令）

执行 gh 命令，获取 PR 信息和差异。

```typescript
interface GHCommandInput {
  args: string[]    // GH 命令参数数组
}

interface GHCommandOutput {
  stdout: string     // 命令输出
  stderr: string     // 错误输出
  exit_code: number  // 退出码
}
```

**支持的命令模式**：

| 用户需求 | GH 命令 | 说明 |
|----------|---------|------|
| 查看当前分支的 PR | `gh pr view` | PR info |
| 查看当前分支的 PR diff | `gh pr diff` | PR diff |
| 查看指定 PR | `gh pr view <number>` | PR info |
| 查看指定 PR diff | `gh pr diff <number>` | PR diff |
| 列出 PR | `gh pr list` | PR list |
| 查看 PR 评论 | `gh pr review <number> --comments` | PR reviews |

---

## 3. 如何确定审查范围

Agent 需要根据用户输入，自动判断要审查什么。

### 3.1 输入模式识别

```
用户输入                          →  审查范围
────────────────────────────────────────────────────
"review 当前分支"                →  diff against base branch
"帮我 review 我的代码"           →  diff against base branch
"review commit xxx"              →  specific commit
"review 最后一个 commit"         →  HEAD commit
"review PR" / "review pull request" → current PR
"review pr 123"                  →  specific PR
"review staged changes"          →  git diff --cached
"review unstaged changes"        →  git diff
"review main 分支"               →  diff main..HEAD
```

### 3.2 智能检测 Base Branch

当用户说"review 当前分支"时，需要自动检测 base branch：

```python
async def detect_base_branch() -> str:
    # 1. 检查当前分支的 upstream
    result = await git_command(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if result.success:
        return result.stdout.split("/")[-1]  # origin/main -> main

    # 2. 尝试 common base branches
    for branch in ["main", "master", "develop", "dev"]:
        result = await git_command(["merge-base", "--is-ancestor", "HEAD", branch])
        if result.exit_code == 0:
            return branch

    return "main"  # 默认
```

### 3.3 GitHub PR 检测

当用户提到 PR 时：

```python
async def get_pr_info(user_input: str) -> dict | None:
    # 1. 检查是否是数字（PR 号）
    if user_input.isdigit():
        return {"type": "pr_number", "value": user_input}

    # 2. 检查是否是 URL
    if "github.com" in user_input:
        # 提取 owner/repo/pr-number
        return {"type": "url", "value": user_input}

    # 3. 检查是否是 "current" 或 "this"
    if "current" in user_input.lower() or "this" in user_input.lower():
        return {"type": "current", "value": None}

    # 4. 尝试作为 branch name 查找 PR
    result = await gh_command(["pr", "list", "--head", user_input, "--json", "number"])
    # 解析结果...

    return None
```

---

## 4. 核心模块设计

### 4.1 Review Scope Detector

负责解析用户输入，确定审查范围。

```python
class ReviewScopeDetector:
    """解析用户输入，确定审查范围"""

    async def detect(self, user_input: str) -> ReviewScope:
        """根据用户输入确定审查范围"""

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

        # Stage 相关
        if "staged" in user_lower:
            return ReviewScope(type="staged")
        if "unstaged" in user_lower:
            return ReviewScope(type="unstaged")

        # 默认：审查当前分支相对于 base 的变更
        return await self._detect_default_scope()


class ReviewScope:
    """审查范围"""
    type: str  # "pr" | "commit" | "branch" | "staged" | "unstaged"
    value: str | None  # PR号、commit hash、branch名等
    base_branch: str | None  # 相对分支（用于 branch 类型）
```

### 4.2 Diff Fetcher

负责获取代码差异。

```python
class DiffFetcher:
    """获取代码差异"""

    async def get_diff(self, scope: ReviewScope) -> str:
        """根据审查范围获取差异"""

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

        return ""

    async def _get_pr_diff(self, pr: str | None) -> str:
        """获取 PR diff"""
        if pr:
            result = await gh_command(["pr", "diff", pr])
        else:
            result = await gh_command(["pr", "diff"])
        return result.stdout

    async def _get_commit_diff(self, commit: str) -> str:
        """获取 commit diff"""
        result = await git_command(["show", commit, "--format="])
        return result.stdout

    async def _get_branch_diff(self, branch: str, base: str) -> str:
        """获取 branch diff"""
        result = await git_command(["diff", f"{base}..HEAD"])
        return result.stdout
```

### 4.3 Context Reader

负责读取文件获取上下文。

```python
class ContextReader:
    """读取文件获取上下文"""

    async def read_changed_files(self, diff: str) -> dict[str, str]:
        """读取 diff 中涉及的所有文件"""

        # 从 diff 中提取文件名
        files = self._extract_files_from_diff(diff)

        # 读取每个文件
        contents = {}
        for file in files:
            result = await read_file(file)
            if result.success:
                contents[file] = result.content

        return contents

    def _extract_files_from_diff(self, diff: str) -> list[str]:
        """从 diff 中提取文件列表"""
        files = []
        for line in diff.split("\n"):
            if line.startswith("diff --git"):
                # 提取文件名 a/src/file.py b/src/file.py
                parts = line.split()
                if len(parts) >= 4:
                    files.append(parts[2][2:])  # 去掉 a/ 或 b/
        return list(set(files))
```

### 4.4 Review Analyzer

负责分析代码问题。

```python
class ReviewAnalyzer:
    """分析代码问题"""

    async def analyze(
        self,
        diff: str,
        file_contents: dict[str, str]
    ) -> ReviewReport:
        """分析代码，生成审查报告"""

        issues = []

        for file_path, content in file_contents.items():
            # 获取该文件在 diff 中的变更
            file_diff = self._extract_file_diff(diff, file_path)

            # 分析各类问题
            issues.extend(await self._analyze_bugs(file_path, file_diff, content))
            issues.extend(await self._analyze_structure(file_path, file_diff, content))
            issues.extend(await self._analyze_security(file_path, file_diff, content))

        return ReviewReport(
            scope=scope,
            issues=issues,
            summary=self._generate_summary(issues)
        )

    async def _analyze_bugs(self, file_path: str, diff: str, full_content: str) -> list[Issue]:
        """分析潜在的 bug"""
        issues = []

        # 检查常见的 bug 模式
        bug_patterns = [
            (r"if.*==.*null", "可能的空指针"),
            (r"\.exec\(", "使用 exec 可能存在安全风险"),
            (r"eval\(", "使用 eval 可能存在安全风险"),
            (r"catch.*pass", "异常被静默吞掉"),
        ]

        for pattern, description in bug_patterns:
            matches = re.finditer(pattern, diff)
            for match in matches:
                issues.append(Issue(
                    severity="major",
                    type="bug",
                    file=file_path,
                    description=description,
                    line=self._get_line_number(diff, match.start())
                ))

        return issues
```

### 4.5 Agent Loop

核心循环逻辑。

```python
async def run_code_review_agent(user_input: str) -> ReviewReport:
    """运行代码审查 Agent"""

    # 1. 确定审查范围
    scope = await scope_detector.detect(user_input)

    # 2. 获取差异
    diff = await diff_fetcher.get_diff(scope)

    if not diff:
        return ReviewReport(
            scope=scope,
            issues=[],
            summary="没有发现代码变更"
        )

    # 3. 读取涉及的文件获取上下文
    file_contents = await context_reader.read_changed_files(diff)

    # 4. 分析代码问题
    report = await analyzer.analyze(diff, file_contents, scope)

    return report
```

---

## 5. 数据结构

### 5.1 ReviewScope

```typescript
interface ReviewScope {
  type: "pr" | "commit" | "branch" | "staged" | "unstaged"
  value?: string      // PR号、commit hash、branch名
  base_branch?: string // 相对分支
  description?: string // 描述
}
```

### 5.2 Issue

```typescript
interface Issue {
  severity: "critical" | "major" | "minor"
  type: "bug" | "security" | "structure" | "performance" | "style"
  file: string
  line?: number
  description: string
  suggestion?: string  // 修复建议
}
```

### 5.3 ReviewReport

```typescript
interface ReviewReport {
  scope: ReviewScope
  issues: Issue[]
  summary: string
  metadata?: {
    files_changed: number
    lines_added: number
    lines_removed: number
  }
}
```

---

## 6. 使用示例

### 6.1 审查当前分支

**用户输入**：
```
帮我 review 当前分支的代码
```

**Agent 行为**：
```
1. 检测当前分支名：feature/login
2. 尝试检测 base branch：main
3. 执行：git diff main..HEAD
4. 读取变更的文件
5. 分析代码问题
6. 输出审查报告
```

### 6.2 审查特定 Commit

**用户输入**：
```
review commit abc123
```

**Agent 行为**：
```
1. 确认 commit hash：abc123
2. 执行：git show abc123
3. 读取该 commit 修改的文件
4. 分析代码问题
5. 输出审查报告
```

### 6.3 审查 PR

**用户输入**：
```
帮我 review 这个 PR
```

**Agent 行为**：
```
1. 执行：gh pr view（获取当前分支关联的 PR）
2. 执行：gh pr diff（获取 PR 的 diff）
3. 读取修改的文件
4. 分析代码问题
5. 输出审查报告
```

### 6.4 审查 PR #123

**用户输入**：
```
review pr 123
```

**Agent 行为**：
```
1. 执行：gh pr view 123
2. 执行：gh pr diff 123
3. 读取修改的文件
4. 分析代码问题
5. 输出审查报告
```

---

## 7. 错误处理

### 7.1 常见错误

| 错误场景 | 处理方式 |
|----------|----------|
| 没有变更需要审查 | 输出提示："当前没有发现代码变更" |
| Git 命令失败 | 输出错误信息，建议检查 git 状态 |
| GH 命令失败 | 提示可能没有安装 gh 或没有登录 |
| 文件读取失败 | 跳过该文件，在报告中注明 |
| 找不到 base branch | 尝试 common names 或提示用户指定 |

### 7.2 回退策略

```python
async def get_diff_with_fallback(scope: ReviewScope) -> str:
    """带回退的 diff 获取"""

    # 尝试 primary 方式
    diff = await diff_fetcher.get_diff(scope)
    if diff:
        return diff

    # 回退：尝试其他方式
    if scope.type == "branch":
        # 尝试不同的 base branch
        for base in ["main", "master", "develop"]:
            diff = await git_command(["diff", f"{base}..HEAD"])
            if diff:
                return diff

    return ""
```

---

## 8. 文件结构

```
code-review-agent/
├── prompts/
│   └── system.md          # System prompt
├── src/
│   ├── __init__.py
│   ├── types.py           # 数据类型定义
│   ├── tools/
│   │   ├── git.py         # Git 工具
│   │   ├── gh.py          # GH 工具
│   │   ├── reader.py      # 文件读取
│   │   └── writer.py      # 文件写入
│   ├── core/
│   │   ├── scope_detector.py  # 范围检测
│   │   ├── diff_fetcher.py    # Diff 获取
│   │   ├── context_reader.py  # 上下文读取
│   │   └── analyzer.py        # 问题分析
│   └── agent.py           # Agent 主逻辑
└── examples/
    └── ...
```

---

## 9. 依赖

- **simple-agent**: 核心 Agent 框架
- **PyGithub** (可选): Python GitHub API 封装
- **GitPython** (可选): Python Git 封装

---

## 10. 后续扩展

- **支持更多 Git 托管平台**：Gitee、GitLab
- **代码质量检查集成**：集成 pylint、eslint 等
- **自动化修复建议**：基于 AI 生成修复代码
- **审查历史记录**：保存和查询历史审查
