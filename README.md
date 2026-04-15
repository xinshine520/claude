# pg-mcp

基于 **模型上下文协议（MCP）** 的自然语言 PostgreSQL 查询服务：用自然语言提问，由服务生成**只读、经校验**的 SQL 并返回结果。

## 功能概览

| 能力 | 说明 |
|------|------|
| **自然语言 → SQL** | 例如「当前有多少用户？」→ 安全、只读的 SQL |
| **多库** | 支持多个数据库别名；可自动选择或每次指定 |
| **Schema 感知** | 自动发现库表结构，为生成 SQL 提供上下文 |
| **安全** | SQLGlot AST 校验、只读事务、危险函数拦截 |
| **可选结果校验** | LLM 对结果做校验（`metadata` / `sample` 模式） |

## 快速开始

### 1. 安装依赖

```bash
cd pg-mcp
uv sync
# 或：pip install -e ".[dev]"
```

Windows 上若已安装 [uv](https://github.com/astral-sh/uv)，在项目目录执行 `uv sync` 即可。

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，至少配置：

```bash
# 必填：数据库（逗号分隔别名）
PG_MCP_DATABASES=mydb
PG_MCP_MYDB_URL=postgresql://user:password@localhost:5432/mydb

# 必填：LLM（DeepSeek / OpenAI 兼容接口）
PG_MCP_LLM_API_KEY=sk-your-api-key
PG_MCP_LLM_BASE_URL=https://api.deepseek.com
PG_MCP_LLM_MODEL=deepseek-chat
```

### 3. 启动服务

| 传输方式 | 适用场景 | 命令示例 |
|----------|----------|----------|
| **stdio（默认）** | Cursor、Claude Desktop 等本地拉起进程 | `python -m pg_mcp` |
| **SSE（远程）** | 需单独端口、SSE 协议 | `python -m pg_mcp --transport sse --port 8000` |
| **HTTP / Streamable HTTP** | **推荐**：Cursor 通过 URL 连接 MCP | `python -m pg_mcp --transport http --port 18080` |

**为何推荐 HTTP 给 Cursor URL 模式？**  
Cursor 期望单一端点同时处理 GET 与 POST。SSE 模式下路径分离（如 GET `/sse`、POST `/messages/`），容易出现 **POST 405 Method Not Allowed**。使用 `--transport http` 可避免该问题。

### 4. 在 Cursor 中配置 MCP

**stdio（由 Cursor 启动子进程）**：

```json
{
  "pg-mcp": {
    "command": "python",
    "args": ["-m", "pg_mcp"],
    "env": {
      "PG_MCP_DATABASES": "mydb",
      "PG_MCP_MYDB_URL": "postgresql://user:pass@localhost:5432/mydb",
      "PG_MCP_LLM_API_KEY": "sk-...",
      "PG_MCP_LLM_BASE_URL": "https://api.deepseek.com",
      "PG_MCP_LLM_MODEL": "deepseek-chat"
    }
  }
}
```

**URL（连接已启动的远程服务，须使用 `--transport http`）**：

```json
{
  "pg-mcp": {
    "url": "http://127.0.0.1:18080/mcp"
  }
}
```

先在本机启动服务，例如：

```bash
uv run pg-mcp --transport http --port 18080
```

## 环境变量参考

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PG_MCP_DATABASES` | `""` | 数据库别名，逗号分隔 |
| `PG_MCP_{ALIAS}_URL` | — | 别名对应连接串 |
| `PG_MCP_LLM_API_KEY` | — | LLM API Key |
| `PG_MCP_LLM_BASE_URL` | `https://api.deepseek.com` | LLM Base URL |
| `PG_MCP_LLM_MODEL` | `deepseek-chat` | 模型名 |
| `PG_MCP_STATEMENT_TIMEOUT` | `30s` | 查询超时 |
| `PG_MCP_DEFAULT_MAX_ROWS` | `100` | 单次返回最大行数 |
| `PG_MCP_VERIFY_MODE` | `off` | `off` \| `metadata` \| `sample` |
| `PG_MCP_LOG_LEVEL` | `INFO` | 日志级别 |

更多项见仓库内 `.env.example`。

## `query` 工具参数

- `question`（字符串）：自然语言问题  
- `database`（可选）：数据库别名；省略时可自动选择  
- `return_mode`：`"result"`（默认）或 `"sql"`  
- `max_rows`（整数）：最大返回行数（默认 100）  
- `verify_result`（布尔）：在 `verify_mode` 为 `metadata` / `sample` 时是否启用 LLM 校验  

## 开发与测试

```bash
# 单元测试（无需 Docker）
uv run pytest -m "not integration"

# 集成测试（需要本机 Docker PostgreSQL）
uv run pytest -m integration

# E2E（Docker + 种子数据）
docker compose -f tests/docker-compose.yml up -d
psql $PG_MCP_E2E_DSN -f tests/fixtures/seed.sql
uv run pytest -m e2e
```

测试库与数据规模说明见 `fixtures/README.md`。

## 高级能力（Phase 9–11）

### Phase 9：按库安全策略

每个数据库可通过环境变量单独限制访问范围：

| 变量 | 格式 | 说明 |
|------|------|------|
| `PG_MCP_{ALIAS}_ALLOWED_SCHEMAS` | 逗号分隔 | 覆盖全局 `search_path`，如 `analytics,reporting` |
| `PG_MCP_{ALIAS}_ALLOWED_TABLES` | 逗号分隔 | 白名单：仅允许访问这些表 |
| `PG_MCP_{ALIAS}_DENIED_TABLES` | 逗号分隔 | 黑名单：禁止访问的表 |
| `PG_MCP_{ALIAS}_ALLOW_EXPLAIN` | `true` / `false` | 是否允许 `EXPLAIN`（默认 `false`） |
| `PG_MCP_{ALIAS}_MAX_ROWS_OVERRIDE` | 整数 | 单库行数上限覆盖 |

**示例**（`analytics` 严格只读部分表，`readonly` 库禁止敏感表）：

```bash
PG_MCP_DATABASES=analytics,readonly
PG_MCP_ANALYTICS_URL=postgresql://user:pass@localhost:5432/analytics
PG_MCP_ANALYTICS_ALLOWED_SCHEMAS=analytics,reporting
PG_MCP_ANALYTICS_ALLOWED_TABLES=daily_metrics,revenue_summary
PG_MCP_ANALYTICS_MAX_ROWS_OVERRIDE=1000

PG_MCP_READONLY_URL=postgresql://user:pass@localhost:5432/readonly
PG_MCP_READONLY_DENIED_TABLES=secrets,passwords
PG_MCP_READONLY_ALLOW_EXPLAIN=true
```

### Phase 10：韧性可观测

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PG_MCP_RATE_LIMIT_RPM` | `60` | 每分钟最大请求数（`0` 或负数表示关闭） |
| `PG_MCP_LLM_MAX_RETRIES` | `3` | LLM 遇 429 / 5xx 时最大重试次数 |
| `PG_MCP_LLM_RETRY_BASE_DELAY` | `1.0` | 指数退避基准秒数 |
| `PG_MCP_METRICS_ENABLED` | `true` | 通过 structlog 输出流水线指标 |

**行为摘要**：

- **限流**：滑动窗口；超限返回 `RateLimitError`（阶段 `rate_limit`）。  
- **LLM 重试**：429 或 5xx 时指数退避（1s → 2s → 4s …，上限 30s）；4xx 客户端错误不重试。  
- **指标**：开启后每条请求记录 `pipeline_metrics`（含各阶段耗时，如 `ensure_schema_loaded`、`generate_sql`、`execute_sql`）。需将 `LOG_LEVEL` 设为 `INFO` 或 `DEBUG` 以便在日志中查看。  

### Phase 11：模型与测试

内部改进（响应序列化、测试覆盖等），**无新增用户可配项**。

## 安全说明：SSE 与 Bearer Token

在 **SSE** 模式（`--transport sse`）下，配置项 `PG_MCP_ACCESS_TOKEN` 存在，但**应用层未实现强制校验**。生产环境建议在 **反向代理**（如 nginx、Caddy）上完成 Bearer Token 校验，再转发到本服务。

## 许可证

MIT
