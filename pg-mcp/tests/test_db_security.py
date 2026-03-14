"""Tests for per-database security controls (Phase 9)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from pg_mcp.config import DatabaseConfig, ServerConfig
from pg_mcp.errors import ValidationError
from pg_mcp.models import QueryRequest, ReturnMode
from pg_mcp.server import QueryPipeline
from pg_mcp.sql.executor import SQLExecutor
from pg_mcp.sql.validator import SQLValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn_mock():
    """Return a minimal mock asyncpg connection."""
    attr_id = MagicMock()
    attr_id.name = "id"
    attr_id.type = MagicMock()
    attr_id.type.name = "int4"

    prepared = MagicMock()
    prepared.get_attributes.return_value = [attr_id]
    prepared.fetch = AsyncMock(return_value=[])

    conn = AsyncMock()
    conn.prepare = AsyncMock(return_value=prepared)
    conn.execute = AsyncMock()
    tx_ctx = MagicMock()
    tx_ctx.__aenter__ = AsyncMock(return_value=tx_ctx)
    tx_ctx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_ctx)
    return conn


def _make_deps(
    db_config: DatabaseConfig | None = None,
    db_alias: str = "testdb",
    llm_sql: str = "SELECT * FROM users",
):
    """Build a minimal deps dict for QueryPipeline."""
    config = MagicMock(spec=ServerConfig)
    config.default_max_rows = 100
    config.verify_mode = "off"
    config.verify_sample_rows = 5
    config.max_sql_length = 10000
    config.blocked_functions = []
    config.statement_timeout = "30s"
    config.lock_timeout = "5s"
    config.max_field_size = 10240
    config.max_payload_size = 5242880
    config.allowed_schemas = ["public"]

    conn = _make_conn_mock()
    pm = MagicMock()
    pm.pools = {db_alias: MagicMock()}

    @asynccontextmanager
    async def _connection(alias):  # noqa: ARG001
        yield conn

    pm.connection = _connection

    schema_cache = MagicMock()
    schema_cache.get_or_load = AsyncMock(return_value=MagicMock())
    schema_cache.list_databases = MagicMock(return_value=[
        {"name": db_alias, "total_tables": 1, "total_views": 0, "table_names": ["public.users"]}
    ])

    llm = MagicMock()
    llm.chat = AsyncMock(return_value=llm_sql)
    llm.extract_sql = MagicMock(return_value=llm_sql)

    return {
        "config": config,
        "pool_manager": pm,
        "schema_cache": schema_cache,
        "llm_client": llm,
        "db_configs": {db_alias: db_config} if db_config else {},
    }


# ---------------------------------------------------------------------------
# 1. allowed_schemas per-db overrides global schema
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_db_allowed_schemas_used_in_executor():
    """Executor uses db_config.allowed_schemas when non-empty."""
    db_config = DatabaseConfig(
        database="testdb",
        allowed_schemas=["analytics", "reporting"],
    )
    executor = SQLExecutor(
        allowed_schemas=["public"],
        db_config=db_config,
    )
    assert executor._effective_schemas() == ["analytics", "reporting"]


@pytest.mark.asyncio
async def test_global_schemas_used_when_db_config_schemas_empty():
    """Executor falls back to global schemas when db_config.allowed_schemas is empty."""
    db_config = DatabaseConfig(database="testdb")  # allowed_schemas = []
    executor = SQLExecutor(
        allowed_schemas=["public"],
        db_config=db_config,
    )
    assert executor._effective_schemas() == ["public"]


@pytest.mark.asyncio
async def test_per_db_schemas_used_in_pipeline():
    """Pipeline uses per-db search_path when db_config has allowed_schemas."""
    db_config = DatabaseConfig(
        database="testdb",
        allowed_schemas=["analytics"],
    )
    deps = _make_deps(db_config=db_config)
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="Get users",
        database="testdb",
        return_mode=ReturnMode.SQL,
    )
    response = await pipeline.execute(request)
    assert response.error is None
    assert response.sql == "SELECT * FROM users"


# ---------------------------------------------------------------------------
# 2. allowed_tables whitelist
# ---------------------------------------------------------------------------

def test_table_whitelist_allows_listed_table():
    """Whitelisted table passes validation."""
    v = SQLValidator(table_whitelist=["users"])
    v.validate("SELECT * FROM users")


def test_table_whitelist_blocks_non_listed_table():
    """Non-whitelisted table raises TABLE_NOT_ALLOWED."""
    v = SQLValidator(table_whitelist=["users"])
    with pytest.raises(ValidationError) as exc:
        v.validate("SELECT * FROM orders")
    assert exc.value.code == "TABLE_NOT_ALLOWED"
    assert "orders" in exc.value.reason.lower()


def test_table_whitelist_schema_qualified_entry_matches():
    """Whitelist entry 'public.users' matches schema-qualified table."""
    v = SQLValidator(table_whitelist=["public.users"])
    v.validate("SELECT * FROM public.users")


def test_table_whitelist_schema_qualified_blocks_unqualified_table():
    """'public.users' whitelist does NOT match unqualified 'users' reference."""
    v = SQLValidator(table_whitelist=["public.users"])
    # 'users' without schema doesn't match 'public.users'
    with pytest.raises(ValidationError) as exc:
        v.validate("SELECT * FROM users")
    assert exc.value.code == "TABLE_NOT_ALLOWED"


def test_table_whitelist_unqualified_entry_matches_unqualified():
    """Whitelist 'users' matches 'SELECT * FROM users'."""
    v = SQLValidator(table_whitelist=["users"])
    v.validate("SELECT * FROM users")


# ---------------------------------------------------------------------------
# 3. denied_tables blacklist
# ---------------------------------------------------------------------------

def test_table_blacklist_blocks_denied_table():
    """Denied table raises TABLE_BLOCKED."""
    v = SQLValidator(table_blacklist=["secrets"])
    with pytest.raises(ValidationError) as exc:
        v.validate("SELECT * FROM secrets")
    assert exc.value.code == "TABLE_BLOCKED"
    assert "secrets" in exc.value.reason.lower()


def test_table_blacklist_allows_non_denied_table():
    """Non-denied table passes validation."""
    v = SQLValidator(table_blacklist=["secrets"])
    v.validate("SELECT * FROM users")


def test_table_blacklist_schema_qualified_entry():
    """'public.secrets' blacklist blocks 'SELECT * FROM public.secrets'."""
    v = SQLValidator(table_blacklist=["public.secrets"])
    with pytest.raises(ValidationError) as exc:
        v.validate("SELECT * FROM public.secrets")
    assert exc.value.code == "TABLE_BLOCKED"


def test_table_blacklist_schema_qualified_entry_does_not_block_unqualified():
    """'public.secrets' blacklist does NOT block unqualified 'secrets'."""
    v = SQLValidator(table_blacklist=["public.secrets"])
    # 'secrets' alone doesn't match 'public.secrets' entry
    v.validate("SELECT * FROM secrets")


# ---------------------------------------------------------------------------
# 4 & 5. allow_explain per-db
# ---------------------------------------------------------------------------

def test_allow_explain_true_permits_explain():
    """EXPLAIN SELECT 1 passes when allow_explain=True."""
    v = SQLValidator(allow_explain=True)
    v.validate("EXPLAIN SELECT 1")


def test_allow_explain_true_still_blocks_explain_analyze():
    """EXPLAIN ANALYZE still fails even when allow_explain=True."""
    v = SQLValidator(allow_explain=True)
    with pytest.raises(ValidationError) as exc:
        v.validate("EXPLAIN ANALYZE SELECT 1")
    assert exc.value.code == "EXPLAIN_ANALYZE"


def test_allow_explain_false_blocks_explain():
    """EXPLAIN is blocked when allow_explain=False (default)."""
    v = SQLValidator(allow_explain=False)
    with pytest.raises(ValidationError) as exc:
        v.validate("EXPLAIN SELECT 1")
    assert exc.value.code == "EXPLAIN_BLOCKED"


@pytest.mark.asyncio
async def test_per_db_allow_explain_pipeline():
    """Pipeline uses per-db allow_explain setting."""
    db_config = DatabaseConfig(database="testdb", allow_explain=True)
    deps = _make_deps(db_config=db_config, llm_sql="EXPLAIN SELECT 1")
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="Explain query",
        database="testdb",
        return_mode=ReturnMode.SQL,
    )
    response = await pipeline.execute(request)
    # allow_explain=True on db_config → EXPLAIN passes validation
    assert response.error is None
    assert response.sql == "EXPLAIN SELECT 1"


@pytest.mark.asyncio
async def test_per_db_allow_explain_false_pipeline():
    """Pipeline blocks EXPLAIN when db_config.allow_explain=False."""
    db_config = DatabaseConfig(database="testdb", allow_explain=False)
    deps = _make_deps(db_config=db_config, llm_sql="EXPLAIN SELECT 1")
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="Explain query",
        database="testdb",
        return_mode=ReturnMode.SQL,
    )
    response = await pipeline.execute(request)
    assert response.error is not None
    assert response.error.code == "VALIDATION_FAILED"


# ---------------------------------------------------------------------------
# 6. max_rows_override per-db
# ---------------------------------------------------------------------------

def test_max_rows_override_used_when_set():
    """Executor uses db_config.max_rows_override when present."""
    db_config = DatabaseConfig(database="testdb", max_rows_override=25)
    executor = SQLExecutor(db_config=db_config)
    assert executor._effective_max_rows(100) == 25


def test_max_rows_override_ignored_when_not_set():
    """Executor uses caller's max_rows when db_config.max_rows_override is None."""
    db_config = DatabaseConfig(database="testdb")  # max_rows_override=None
    executor = SQLExecutor(db_config=db_config)
    assert executor._effective_max_rows(50) == 50


def test_max_rows_override_with_no_db_config():
    """Executor uses caller's max_rows when db_config is None."""
    executor = SQLExecutor()
    assert executor._effective_max_rows(75) == 75


# ---------------------------------------------------------------------------
# 7. Two databases with different configs don't interfere
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_two_databases_independent_security():
    """Validator for db1 and db2 use independent security settings."""
    db1_config = DatabaseConfig(
        database="db1",
        allowed_tables=["users"],
        allow_explain=True,
    )
    db2_config = DatabaseConfig(
        database="db2",
        denied_tables=["users"],
        allow_explain=False,
    )

    # Create pipeline-style validators for each
    v1 = SQLValidator(
        allow_explain=db1_config.allow_explain,
        table_whitelist=db1_config.allowed_tables,
    )
    v2 = SQLValidator(
        allow_explain=db2_config.allow_explain,
        table_blacklist=db2_config.denied_tables,
    )

    # db1: users allowed, explain allowed
    v1.validate("SELECT * FROM users")
    v1.validate("EXPLAIN SELECT * FROM users")

    # db2: users blocked
    with pytest.raises(ValidationError) as exc:
        v2.validate("SELECT * FROM users")
    assert exc.value.code == "TABLE_BLOCKED"

    # db2: explain blocked
    with pytest.raises(ValidationError) as exc:
        v2.validate("EXPLAIN SELECT 1")
    assert exc.value.code == "EXPLAIN_BLOCKED"

    # db1 validator unaffected by db2 settings
    v1.validate("SELECT * FROM users")
