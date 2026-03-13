"""E2E tests: Docker PG + Mock LLM."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pg_mcp.server import QueryPipeline

pytest.importorskip("asyncpg")

E2E_PG_URL = os.environ.get(
    "PG_MCP_E2E_DSN",
    "postgresql://postgres:postgres@localhost:5433/pg_mcp_test",
)


async def _pg_available() -> bool:
    """Check if test PostgreSQL is available."""
    try:
        import asyncpg

        conn = await asyncpg.connect(E2E_PG_URL)
        await conn.close()
        return True
    except Exception:
        return False


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_simple_query(e2e_pg_url):
    """Scenario 1: 简单查询 - 查询所有用户, 返回正确行数和列结构."""
    if not await _pg_available():
        pytest.skip("PostgreSQL not available (run: docker compose -f tests/docker-compose.yml up -d)")

    from pg_mcp.config import ServerConfig
    from pg_mcp.db.pool_manager import PoolManager
    from pg_mcp.llm.client import LLMClient
    from pg_mcp.models import QueryRequest, ReturnMode
    from pg_mcp.schema.cache import SchemaCache

    with patch.dict(
        os.environ,
        {"PG_MCP_DATABASES": "e2edb", "PG_MCP_E2EDB_URL": e2e_pg_url},
        clear=False,
    ):
        config = ServerConfig(databases="e2edb", default_max_rows=100)
        pool_manager = PoolManager(config)
        await pool_manager.initialize()

    if "e2edb" not in pool_manager.pools:
        pytest.skip("Could not connect to test database")

    schema_cache = SchemaCache()
    await schema_cache.warm_up(pool_manager)

    llm = MagicMock(spec=LLMClient)
    llm.chat = AsyncMock(return_value="SELECT * FROM users")
    llm.extract_sql = MagicMock(return_value="SELECT * FROM users")

    deps = {
        "config": config,
        "pool_manager": pool_manager,
        "schema_cache": schema_cache,
        "llm_client": llm,
    }
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="查询所有用户",
        database="e2edb",
        return_mode=ReturnMode.RESULT,
    )
    response = await pipeline.execute(request)
    await pool_manager.close()

    assert response.error is None
    assert response.result is not None
    assert len(response.result.columns) >= 2  # id, name, email, created_at
    assert response.result.returned_row_count >= 5
    assert any(c.name == "name" or c.name == "email" for c in response.result.columns)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_sql_mode(e2e_pg_url):
    """Scenario 4: sql 模式 - 仅返回 SQL, 不执行."""
    if not await _pg_available():
        pytest.skip("PostgreSQL not available")

    from pg_mcp.config import ServerConfig
    from pg_mcp.db.pool_manager import PoolManager
    from pg_mcp.llm.client import LLMClient
    from pg_mcp.models import QueryRequest, ReturnMode
    from pg_mcp.schema.cache import SchemaCache

    with patch.dict(
        os.environ,
        {"PG_MCP_DATABASES": "e2edb", "PG_MCP_E2EDB_URL": e2e_pg_url},
        clear=False,
    ):
        config = ServerConfig(databases="e2edb")
        pool_manager = PoolManager(config)
        await pool_manager.initialize()

    if "e2edb" not in pool_manager.pools:
        pytest.skip("Could not connect to test database")

    schema_cache = SchemaCache()
    await schema_cache.warm_up(pool_manager)

    llm = MagicMock(spec=LLMClient)
    llm.chat = AsyncMock(return_value="SELECT * FROM users")
    llm.extract_sql = MagicMock(return_value="SELECT * FROM users")

    deps = {
        "config": config,
        "pool_manager": pool_manager,
        "schema_cache": schema_cache,
        "llm_client": llm,
    }
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="显示查询所有用户的 SQL",
        database="e2edb",
        return_mode=ReturnMode.SQL,
    )
    response = await pipeline.execute(request)
    await pool_manager.close()

    assert response.error is None
    assert response.sql == "SELECT * FROM users"
    assert response.result is None


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_empty_result(e2e_pg_url):
    """Scenario 6: 空结果集 - rows=[], columns 仍有值."""
    if not await _pg_available():
        pytest.skip("PostgreSQL not available")

    from pg_mcp.config import ServerConfig
    from pg_mcp.db.pool_manager import PoolManager
    from pg_mcp.llm.client import LLMClient
    from pg_mcp.models import QueryRequest, ReturnMode
    from pg_mcp.schema.cache import SchemaCache

    with patch.dict(
        os.environ,
        {"PG_MCP_DATABASES": "e2edb", "PG_MCP_E2EDB_URL": e2e_pg_url},
        clear=False,
    ):
        config = ServerConfig(databases="e2edb")
        pool_manager = PoolManager(config)
        await pool_manager.initialize()

    if "e2edb" not in pool_manager.pools:
        pytest.skip("Could not connect to test database")

    schema_cache = SchemaCache()
    await schema_cache.warm_up(pool_manager)

    llm = MagicMock(spec=LLMClient)
    llm.chat = AsyncMock(return_value="SELECT * FROM users WHERE id = 99999")
    llm.extract_sql = MagicMock(return_value="SELECT * FROM users WHERE id = 99999")

    deps = {
        "config": config,
        "pool_manager": pool_manager,
        "schema_cache": schema_cache,
        "llm_client": llm,
    }
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="Find user with id 99999",
        database="e2edb",
        return_mode=ReturnMode.RESULT,
    )
    response = await pipeline.execute(request)
    await pool_manager.close()

    assert response.error is None
    assert response.result is not None
    assert response.result.rows == []
    assert len(response.result.columns) > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_nonexistent_database(e2e_pg_url):
    """Scenario 7: 不存在的数据库 - DB_UNAVAILABLE/DB_AMBIGUOUS 错误."""
    if not await _pg_available():
        pytest.skip("PostgreSQL not available")

    from pg_mcp.config import ServerConfig
    from pg_mcp.db.pool_manager import PoolManager
    from pg_mcp.llm.client import LLMClient
    from pg_mcp.models import QueryRequest, ReturnMode
    from pg_mcp.schema.cache import SchemaCache

    with patch.dict(
        os.environ,
        {"PG_MCP_DATABASES": "e2edb", "PG_MCP_E2EDB_URL": e2e_pg_url},
        clear=False,
    ):
        config = ServerConfig(databases="e2edb")
        pool_manager = PoolManager(config)
        await pool_manager.initialize()

    if "e2edb" not in pool_manager.pools:
        pytest.skip("Could not connect to test database")

    schema_cache = SchemaCache()
    await schema_cache.warm_up(pool_manager)

    llm = MagicMock(spec=LLMClient)
    llm.chat = AsyncMock(return_value="SELECT 1")
    llm.extract_sql = MagicMock(return_value="SELECT 1")

    deps = {
        "config": config,
        "pool_manager": pool_manager,
        "schema_cache": schema_cache,
        "llm_client": llm,
    }
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="Query",
        database="nonexistent_db",
        return_mode=ReturnMode.RESULT,
    )
    response = await pipeline.execute(request)
    await pool_manager.close()

    assert response.error is not None
    assert "nonexistent" in response.error.message.lower() or "not" in response.error.message.lower()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_e2e_validation_failed(e2e_pg_url):
    """Scenario 8: LLM 生成危险 SQL - VALIDATION_FAILED 错误."""
    if not await _pg_available():
        pytest.skip("PostgreSQL not available")

    from pg_mcp.config import ServerConfig
    from pg_mcp.db.pool_manager import PoolManager
    from pg_mcp.llm.client import LLMClient
    from pg_mcp.models import QueryRequest, ReturnMode
    from pg_mcp.schema.cache import SchemaCache

    with patch.dict(
        os.environ,
        {"PG_MCP_DATABASES": "e2edb", "PG_MCP_E2EDB_URL": e2e_pg_url},
        clear=False,
    ):
        config = ServerConfig(databases="e2edb")
        pool_manager = PoolManager(config)
        await pool_manager.initialize()

    if "e2edb" not in pool_manager.pools:
        pytest.skip("Could not connect to test database")

    schema_cache = SchemaCache()
    await schema_cache.warm_up(pool_manager)

    llm = MagicMock(spec=LLMClient)
    llm.chat = AsyncMock(return_value="SELECT pg_sleep(100)")
    llm.extract_sql = MagicMock(return_value="SELECT pg_sleep(100)")

    deps = {
        "config": config,
        "pool_manager": pool_manager,
        "schema_cache": schema_cache,
        "llm_client": llm,
    }
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="Sleep",
        database="e2edb",
        return_mode=ReturnMode.RESULT,
    )
    response = await pipeline.execute(request)
    await pool_manager.close()

    assert response.error is not None
    assert response.error.code == "VALIDATION_FAILED"
