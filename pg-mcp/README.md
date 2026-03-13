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

### 4. Cursor MCP config

```json
{
  "mcpServers": {
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
}
```

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

## Security Notes

### SSE Mode and Bearer Token Authentication

When running in SSE mode (`--transport sse`), the `PG_MCP_ACCESS_TOKEN` config field is available but token enforcement is not implemented at the application level. For production deployments, use a reverse proxy (e.g., nginx, Caddy) to enforce Bearer token authentication before requests reach the server.

## License

MIT
