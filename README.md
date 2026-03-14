# pg-mcp

Natural language PostgreSQL query MCP server. Query your PostgreSQL databases using natural language via the Model Context Protocol (MCP).

## Features

- **Natural language to SQL**: Converts questions like "How many users do we have?" into safe, read-only SQL
- **Multi-database support**: Configure multiple databases; auto-select or specify per query
- **Schema-aware**: Automatically discovers schema and retrieves relevant tables for context
- **Security**: SQL validation (SQLGlot AST), read-only transactions, blocked dangerous functions
- **Optional verification**: LLM-based result verification (metadata or sample mode)

## Quick Start

### 1. Install

```bash
cd pg-mcp
uv sync
# or: pip install -e ".[dev]"
```

### 2. Configure

Copy `.env.example` to `.env` and set:

```bash
# Required: database(s)
PG_MCP_DATABASES=mydb
PG_MCP_MYDB_URL=postgresql://user:password@localhost:5432/mydb

# Required: LLM (DeepSeek / OpenAI compatible)
PG_MCP_LLM_API_KEY=sk-your-api-key
PG_MCP_LLM_BASE_URL=https://api.deepseek.com
PG_MCP_LLM_MODEL=deepseek-chat
```

### 3. Run

**stdio (default)** – for Cursor, Claude Desktop, etc.:

```bash
python -m pg_mcp
```

**SSE (remote)**:

```bash
python -m pg_mcp --transport sse --port 8000
```

**HTTP / Streamable HTTP (recommended for Cursor URL mode)**:

```bash
python -m pg_mcp --transport http --port 18080
```

Use `--transport http` when connecting via URL. Cursor expects a single endpoint for both GET and POST; SSE uses separate paths (`/sse` for GET, `/messages/` for POST) which can cause `405 Method Not Allowed` on POST.

### 4. Cursor MCP config

**stdio (spawn process)**:

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

**URL (remote server, use `--transport http`)**:

```json
{
  "pg-mcp": {
    "url": "http://127.0.0.1:18080/mcp"
  }
}
```

Start the server with: `uv run pg-mcp --transport http --port 18080`

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_MCP_DATABASES` | `""` | Comma-separated database aliases |
| `PG_MCP_{ALIAS}_URL` | — | Connection URL for alias |
| `PG_MCP_LLM_API_KEY` | — | LLM API key |
| `PG_MCP_LLM_BASE_URL` | `https://api.deepseek.com` | LLM API base URL |
| `PG_MCP_LLM_MODEL` | `deepseek-chat` | Model name |
| `PG_MCP_STATEMENT_TIMEOUT` | `30s` | Query timeout |
| `PG_MCP_DEFAULT_MAX_ROWS` | `100` | Max rows per result |
| `PG_MCP_VERIFY_MODE` | `off` | `off` \| `metadata` \| `sample` |
| `PG_MCP_LOG_LEVEL` | `INFO` | Log level |

See `.env.example` for all options.

## Query Tool

The `query` tool accepts:

- `question` (str): Natural language question
- `database` (str, optional): Database alias; auto-selected if omitted
- `return_mode` (str): `"result"` (default) or `"sql"`
- `max_rows` (int): Max rows to return (default: 100)
- `verify_result` (bool): Enable LLM verification when `verify_mode` is metadata/sample

## Development

### Tests

```bash
# Unit tests (no Docker)
uv run pytest -m "not integration"

# Integration tests (require Docker PostgreSQL)
uv run pytest -m integration

# E2E tests (Docker + seed)
docker compose -f tests/docker-compose.yml up -d
psql $PG_MCP_E2E_DSN -f tests/fixtures/seed.sql
uv run pytest -m e2e
```

### Fixtures

See `fixtures/README.md` for test database setup (small, medium, large).

## Advanced Features (Phase 9–11)

### Phase 9: Per-Database Security Control

Each database can have its own access rules via environment variables:

| Variable | Format | Description |
|----------|--------|-------------|
| `PG_MCP_{ALIAS}_ALLOWED_SCHEMAS` | Comma-separated | Override global `search_path` (e.g. `analytics,reporting`) |
| `PG_MCP_{ALIAS}_ALLOWED_TABLES` | Comma-separated | Whitelist: only these tables can be accessed (e.g. `users,orders`) |
| `PG_MCP_{ALIAS}_DENIED_TABLES` | Comma-separated | Blacklist: these tables are blocked (e.g. `secrets,audit_log`) |
| `PG_MCP_{ALIAS}_ALLOW_EXPLAIN` | `true`/`false` | Allow `EXPLAIN` (default: `false`) |
| `PG_MCP_{ALIAS}_MAX_ROWS_OVERRIDE` | Integer | Per-db row limit override |

**Example `.env`** (database `analytics` with strict access):

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

---

### Phase 10: Resilience & Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `PG_MCP_RATE_LIMIT_RPM` | `60` | Max requests per minute (0 or negative = disabled) |
| `PG_MCP_LLM_MAX_RETRIES` | `3` | Max retries for 429/5xx LLM errors |
| `PG_MCP_LLM_RETRY_BASE_DELAY` | `1.0` | Base delay (seconds) for exponential backoff |
| `PG_MCP_METRICS_ENABLED` | `true` | Emit pipeline metrics via structlog |

**Behavior:**

- **Rate limiting**: Sliding-window; over-limit requests return `RateLimitError` (stage `rate_limit`).
- **LLM retry**: On 429 (rate limit) or 5xx (server error), LLM calls retry with exponential backoff (1s → 2s → 4s …, cap 30s). 4xx (client error) are not retried.
- **Metrics**: When enabled, each request logs a `pipeline_metrics` event with stage durations (e.g. `ensure_schema_loaded`, `generate_sql`, `execute_sql`). Ensure `LOG_LEVEL=INFO` or `DEBUG` to see them.

---

### Phase 11: Model & Test Improvements

Internal changes only (no new config): response model serialization fixes and higher test coverage. No user-facing configuration.

---

## Security Notes

### SSE Mode and Bearer Token Authentication

When running in SSE mode (`--transport sse`), the `PG_MCP_ACCESS_TOKEN` config field is available but token enforcement is not implemented at the application level. For production deployments, use a reverse proxy (e.g., nginx, Caddy) to enforce Bearer token authentication before requests reach the server.

## License

MIT
