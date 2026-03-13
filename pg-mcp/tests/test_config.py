"""Tests for config module."""

from __future__ import annotations



from pg_mcp.config import (
    LLMConfig,
    ServerConfig,
    parse_databases_config,
)
from pydantic import SecretStr


def test_server_config_defaults():
    """ServerConfig has expected defaults."""
    config = ServerConfig()
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
