"""Integration tests for SQL executor (requires PostgreSQL)."""

from __future__ import annotations

import os

import pytest

from pg_mcp.errors import ExecutionError
from pg_mcp.models import ColumnDef, QueryResult
from pg_mcp.sql.executor import SQLExecutor

pytest.importorskip("asyncpg")

# Check for PG availability
PG_DSN = os.environ.get(
    "PG_MCP_TEST_DSN",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)


@pytest.fixture
def executor():
    return SQLExecutor(
        statement_timeout="5s",
        lock_timeout="2s",
        max_field_size=100,
        max_payload_size=1000,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_executor_requires_pg(executor):
    """Skip if PostgreSQL is not available."""
    try:
        import asyncpg

        conn = await asyncpg.connect(PG_DSN)
        await conn.close()
    except Exception:
        pytest.skip("PostgreSQL not available")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_executor_simple_select(executor):
    """Execute simple SELECT and get result."""
    import asyncpg

    try:
        pool = await asyncpg.create_pool(
            PG_DSN, min_size=1, max_size=2, command_timeout=5
        )
    except Exception:
        pytest.skip("PostgreSQL not available")

    # Create a simple DatabasePool-like object
    class FakePool:
        def __init__(self, pool):
            self.pool = pool

        async def acquire(self):
            return await self.pool.acquire()

        def release(self, conn):
            self.pool.release(conn)

    fake_pool = FakePool(pool)
    try:
        result = await executor.execute_readonly(
            fake_pool, "SELECT 1 AS num, 'hello' AS msg", max_rows=10
        )
        assert isinstance(result, QueryResult)
        assert len(result.columns) == 2
        assert result.columns[0].name == "num"
        assert result.columns[1].name == "msg"
        assert result.returned_row_count == 1
        assert result.rows == [[1, "hello"]]
        assert result.truncated is False
    finally:
        await pool.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_executor_empty_result(executor):
    """Empty result returns correct column metadata."""
    import asyncpg

    try:
        pool = await asyncpg.create_pool(
            PG_DSN, min_size=1, max_size=2, command_timeout=5
        )
    except Exception:
        pytest.skip("PostgreSQL not available")

    class FakePool:
        def __init__(self, pool):
            self.pool = pool

        async def acquire(self):
            return await self.pool.acquire()

        def release(self, conn):
            self.pool.release(conn)

    fake_pool = FakePool(pool)
    try:
        result = await executor.execute_readonly(
            fake_pool,
            "SELECT 1 AS a, 2 AS b WHERE 1 = 0",
            max_rows=10,
        )
        assert isinstance(result, QueryResult)
        assert len(result.columns) == 2
        assert result.columns[0].name == "a"
        assert result.columns[1].name == "b"
        assert result.returned_row_count == 0
        assert result.rows == []
    finally:
        await pool.close()
