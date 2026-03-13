"""Configuration models loaded from environment variables."""

from __future__ import annotations

import os
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Connection config for a single database."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    host: str = "localhost"
    port: int = 5432
    database: str = ""
    user: str = ""
    password: SecretStr = SecretStr("")
    sslmode: str = "prefer"
    url: str | None = None  # Priority: use connection string if set


class LLMConfig(BaseSettings):
    """LLM API configuration (DeepSeek/OpenAI compatible)."""

    model_config = SettingsConfigDict(env_prefix="PG_MCP_LLM_", extra="ignore")

    api_key: SecretStr = SecretStr("")
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.0


class ServerConfig(BaseSettings):
    """Server-level configuration."""

    model_config = SettingsConfigDict(env_prefix="PG_MCP_", extra="ignore")

    databases: str = ""
    statement_timeout: str = "30s"
    lock_timeout: str = "5s"
    default_max_rows: int = 100
    max_field_size: int = 10240
    max_payload_size: int = 5242880
    pool_size_per_db: int = 5
    max_concurrent_queries: int = 20
    verify_mode: str = "off"
    verify_sample_rows: int = 5
    log_level: str = "INFO"
    access_token: SecretStr | None = None
    max_sql_length: int = 10000
    blocked_functions: list[str] = Field(default_factory=list)
    collect_view_definitions: bool = True
    schema_cache_ttl: float = 3600.0
    max_tables_per_db: int = 500


def parse_databases_config(server_config: ServerConfig) -> dict[str, DatabaseConfig]:
    """
    Parse PG_MCP_DATABASES and PG_MCP_{ALIAS}_* / PG_MCP_{ALIAS}_URL env vars
    into a mapping of alias -> DatabaseConfig.
    """
    aliases_str = server_config.databases.strip()
    if not aliases_str:
        return {}

    aliases = [a.strip() for a in aliases_str.split(",") if a.strip()]
    result: dict[str, DatabaseConfig] = {}

    for alias in aliases:
        prefix = f"PG_MCP_{alias.upper().replace('-', '_')}_"
        url_key = f"{prefix}URL"
        url_val = os.environ.get(url_key)

        if url_val:
            result[alias] = DatabaseConfig(
                url=url_val,
                database="",  # Will be parsed from URL
                user="",
                password=SecretStr(""),
            )
            continue

        fields: dict[str, Any] = {}
        for env_key, env_val in os.environ.items():
            if env_key.startswith(prefix) and env_key != url_key:
                field_name = env_key[len(prefix) :].lower()
                if field_name == "password":
                    fields["password"] = SecretStr(env_val)
                elif field_name == "port":
                    fields["port"] = int(env_val) if env_val.isdigit() else 5432
                else:
                    fields[field_name] = env_val

        if "database" not in fields or not fields.get("database"):
            continue
        result[alias] = DatabaseConfig(**fields)

    return result
