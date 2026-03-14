"""Configuration models loaded from environment variables."""

from __future__ import annotations

import os
from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """Connection config for a single database."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    host: str = "localhost"
    port: int = 5432
    database: str = ""
    user: str = ""
    password: SecretStr = SecretStr("")
    sslmode: str = "prefer"
    url: str | None = None  # Priority: use connection string if set

    # Per-database security overrides (Phase 9)
    allowed_schemas: list[str] = Field(default_factory=list)
    allowed_tables: list[str] | None = None
    denied_tables: list[str] | None = None
    allow_explain: bool = False
    max_rows_override: int | None = None

    # NOTE: access_token reserved for future per-db auth; not enforced at application level
    access_token: SecretStr | None = None


class LLMConfig(BaseSettings):
    """LLM API configuration (DeepSeek/OpenAI compatible)."""

    model_config = SettingsConfigDict(
        env_prefix="PG_MCP_LLM_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    api_key: SecretStr = SecretStr("")
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout: float = 30.0


class ServerConfig(BaseSettings):
    """Server-level configuration."""

    model_config = SettingsConfigDict(
        env_prefix="PG_MCP_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

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
    # NOTE: access_token reserved for future per-db auth; not enforced at application level
    access_token: SecretStr | None = None
    max_sql_length: int = 10000
    blocked_functions: list[str] = Field(default_factory=list)
    collect_view_definitions: bool = True
    schema_cache_ttl: float = 3600.0
    max_tables_per_db: int = 500
    allowed_schemas: list[str] = Field(default_factory=lambda: ["public"])

    # Phase 10: Resilience & Observability
    rate_limit_rpm: int = 60
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0
    metrics_enabled: bool = True


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

        fields: dict[str, Any] = {}

        if url_val:
            fields["url"] = url_val
            fields["database"] = ""
            fields["user"] = ""
            fields["password"] = SecretStr("")

        for env_key, env_val in os.environ.items():
            if not env_key.startswith(prefix) or env_key == url_key:
                continue
            field_name = env_key[len(prefix):].lower()
            if field_name == "password":
                fields["password"] = SecretStr(env_val)
            elif field_name == "port":
                fields["port"] = int(env_val) if env_val.isdigit() else 5432
            elif field_name == "allowed_schemas":
                fields["allowed_schemas"] = [
                    s.strip() for s in env_val.split(",") if s.strip()
                ]
            elif field_name == "allowed_tables":
                parsed = [t.strip() for t in env_val.split(",") if t.strip()]
                fields["allowed_tables"] = parsed if parsed else None
            elif field_name == "denied_tables":
                parsed = [t.strip() for t in env_val.split(",") if t.strip()]
                fields["denied_tables"] = parsed if parsed else None
            elif field_name == "allow_explain":
                fields["allow_explain"] = env_val.lower() in ("true", "1", "yes")
            elif field_name == "max_rows_override":
                try:
                    fields["max_rows_override"] = int(env_val)
                except ValueError:
                    pass
            else:
                fields[field_name] = env_val

        # Skip aliases with neither URL nor database field
        if "url" not in fields and ("database" not in fields or not fields.get("database")):
            continue

        result[alias] = DatabaseConfig(**fields)

    return result
