"""Tests for config module."""

from __future__ import annotations



from pg_mcp.config import (
    LLMConfig,
    ServerConfig,
    parse_databases_config,
)
from pydantic import SecretStr


def test_server_config_defaults(monkeypatch):
    """ServerConfig has expected defaults (isolated from .env)."""
    monkeypatch.delenv("PG_MCP_DATABASES", raising=False)
    monkeypatch.delenv("PG_MCP_STATEMENT_TIMEOUT", raising=False)
    monkeypatch.delenv("PG_MCP_DEFAULT_MAX_ROWS", raising=False)
    monkeypatch.delenv("PG_MCP_MAX_SQL_LENGTH", raising=False)
    monkeypatch.delenv("PG_MCP_POOL_SIZE_PER_DB", raising=False)
    config = ServerConfig(_env_file=None)
    assert config.databases == ""
    assert config.statement_timeout == "30s"
    assert config.default_max_rows == 100
    assert config.max_sql_length == 10000
    assert config.pool_size_per_db == 5


def test_llm_config_env_prefix():
    """LLMConfig uses PG_MCP_LLM_ prefix."""
    config = LLMConfig(api_key=SecretStr("sk-test"))
    assert config.api_key.get_secret_value() == "sk-test"
    assert config.base_url == "https://api.deepseek.com"
    assert config.model == "deepseek-chat"


def test_secret_str_not_leaked():
    """SecretStr values are not exposed in repr/str."""
    config = LLMConfig(api_key=SecretStr("secret-key"))
    assert "secret-key" not in repr(config)
    assert "secret-key" not in str(config)


def test_parse_databases_config_empty():
    """Empty databases string returns empty dict."""
    config = ServerConfig(databases="")
    assert parse_databases_config(config) == {}


def test_parse_databases_config_from_url(monkeypatch):
    """Parse database config from PG_MCP_ALIAS_URL."""
    monkeypatch.setenv("PG_MCP_DATABASES", "mydb")
    monkeypatch.setenv("PG_MCP_MYDB_URL", "postgresql://u:p@localhost:5432/db")
    config = ServerConfig()
    config.databases = "mydb"
    result = parse_databases_config(config)
    assert "mydb" in result
    assert result["mydb"].url == "postgresql://u:p@localhost:5432/db"


def test_parse_databases_config_from_components(monkeypatch):
    """Parse database config from individual env vars."""
    monkeypatch.setenv("PG_MCP_DATABASES", "other")
    monkeypatch.setenv("PG_MCP_OTHER_HOST", "pg.example.com")
    monkeypatch.setenv("PG_MCP_OTHER_PORT", "5433")
    monkeypatch.setenv("PG_MCP_OTHER_DATABASE", "analytics")
    monkeypatch.setenv("PG_MCP_OTHER_USER", "reader")
    monkeypatch.setenv("PG_MCP_OTHER_PASSWORD", "secret")
    config = ServerConfig()
    config.databases = "other"
    result = parse_databases_config(config)
    assert "other" in result
    cfg = result["other"]
    assert cfg.host == "pg.example.com"
    assert cfg.port == 5433
    assert cfg.database == "analytics"
    assert cfg.user == "reader"
    assert cfg.password.get_secret_value() == "secret"


def test_parse_databases_config_skips_missing_database(monkeypatch):
    """Skip aliases without database (or URL) set."""
    monkeypatch.setenv("PG_MCP_DATABASES", "missing,found")
    monkeypatch.setenv("PG_MCP_FOUND_DATABASE", "db")
    monkeypatch.setenv("PG_MCP_FOUND_USER", "u")
    monkeypatch.setenv("PG_MCP_FOUND_PASSWORD", "p")
    config = ServerConfig()
    config.databases = "missing,found"
    result = parse_databases_config(config)
    assert "missing" not in result
    assert "found" in result


# Phase 9: per-db security config

def test_parse_databases_config_allowed_tables(monkeypatch):
    """Per-db allowed_tables parsed from env var."""
    monkeypatch.setenv("PG_MCP_MYDB_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("PG_MCP_MYDB_ALLOWED_TABLES", "users,orders")
    config = ServerConfig()
    config.databases = "mydb"
    result = parse_databases_config(config)
    assert result["mydb"].allowed_tables == ["users", "orders"]


def test_parse_databases_config_denied_tables(monkeypatch):
    """Per-db denied_tables parsed from env var."""
    monkeypatch.setenv("PG_MCP_MYDB_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("PG_MCP_MYDB_DENIED_TABLES", "secrets,audit_log")
    config = ServerConfig()
    config.databases = "mydb"
    result = parse_databases_config(config)
    assert result["mydb"].denied_tables == ["secrets", "audit_log"]


def test_parse_databases_config_allow_explain(monkeypatch):
    """Per-db allow_explain parsed from env var (true/false)."""
    monkeypatch.setenv("PG_MCP_MYDB_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("PG_MCP_MYDB_ALLOW_EXPLAIN", "true")
    config = ServerConfig()
    config.databases = "mydb"
    result = parse_databases_config(config)
    assert result["mydb"].allow_explain is True


def test_parse_databases_config_allow_explain_false(monkeypatch):
    """Per-db allow_explain defaults to False."""
    monkeypatch.setenv("PG_MCP_MYDB_URL", "postgresql://u:p@localhost/db")
    config = ServerConfig()
    config.databases = "mydb"
    result = parse_databases_config(config)
    assert result["mydb"].allow_explain is False


def test_parse_databases_config_max_rows_override(monkeypatch):
    """Per-db max_rows_override parsed from env var."""
    monkeypatch.setenv("PG_MCP_MYDB_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("PG_MCP_MYDB_MAX_ROWS_OVERRIDE", "50")
    config = ServerConfig()
    config.databases = "mydb"
    result = parse_databases_config(config)
    assert result["mydb"].max_rows_override == 50


def test_parse_databases_config_allowed_schemas_per_db(monkeypatch):
    """Per-db allowed_schemas parsed from env var."""
    monkeypatch.setenv("PG_MCP_MYDB_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("PG_MCP_MYDB_ALLOWED_SCHEMAS", "analytics,reporting")
    config = ServerConfig()
    config.databases = "mydb"
    result = parse_databases_config(config)
    assert result["mydb"].allowed_schemas == ["analytics", "reporting"]


# Phase 10: rate limiting and LLM retry config

def test_server_config_rate_limit_defaults():
    """ServerConfig has expected rate limiting defaults."""
    config = ServerConfig()
    assert config.rate_limit_rpm == 60
    assert config.llm_max_retries == 3
    assert config.llm_retry_base_delay == 1.0
    assert config.metrics_enabled is True


def test_server_config_rate_limit_from_env(monkeypatch):
    """rate_limit_rpm and retry config loaded from env."""
    monkeypatch.setenv("PG_MCP_RATE_LIMIT_RPM", "120")
    monkeypatch.setenv("PG_MCP_LLM_MAX_RETRIES", "5")
    monkeypatch.setenv("PG_MCP_LLM_RETRY_BASE_DELAY", "2.0")
    monkeypatch.setenv("PG_MCP_METRICS_ENABLED", "false")
    config = ServerConfig()
    assert config.rate_limit_rpm == 120
    assert config.llm_max_retries == 5
    assert config.llm_retry_base_delay == 2.0
    assert config.metrics_enabled is False
