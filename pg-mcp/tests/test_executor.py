"""Tests for SQL executor."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from pg_mcp.config import DatabaseConfig
from pg_mcp.models import QueryResult
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


# ---------------------------------------------------------------------------
# Unit tests (no PostgreSQL required)
# ---------------------------------------------------------------------------

def _make_mock_conn(rows=None, attrs=None):
    """Create a mock asyncpg connection."""
    if attrs is None:
        a = MagicMock()
        a.name = "val"
        a.type = MagicMock()
        a.type.name = "text"
        attrs = [a]

    prepared = MagicMock()
    prepared.get_attributes.return_value = attrs
    prepared.fetch = AsyncMock(return_value=rows or [])

    conn = AsyncMock()
    conn.prepare = AsyncMock(return_value=prepared)
    conn.execute = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx)
    return conn


@pytest.mark.asyncio
async def test_limit_subquery_wrapping():
    """Executor wraps query in SELECT * FROM (...) LIMIT N+1."""
    conn = _make_mock_conn()
    executor = SQLExecutor()
    await executor.execute_with_connection(conn, "SELECT 1", max_rows=5)
    conn.prepare.assert_called_once()
    sql_arg = conn.prepare.call_args[0][0]
    assert "SELECT * FROM (" in sql_arg
    assert "LIMIT 6" in sql_arg


@pytest.mark.asyncio
async def test_empty_result_has_columns():
    """Empty result still returns column metadata."""
    attr = MagicMock()
    attr.name = "my_col"
    attr.type = MagicMock()
    attr.type.name = "int4"
    conn = _make_mock_conn(rows=[], attrs=[attr])
    executor = SQLExecutor()
    result = await executor.execute_with_connection(conn, "SELECT 1 AS my_col WHERE false", max_rows=10)
    assert isinstance(result, QueryResult)
    assert len(result.columns) == 1
    assert result.columns[0].name == "my_col"
    assert result.rows == []
    assert result.returned_row_count == 0


def test_field_truncation_string():
    """Long strings are truncated with ...[truncated] suffix."""
    executor = SQLExecutor(max_field_size=10)
    rows = [["hello world long text"]]
    result = executor._truncate_fields(rows)
    assert result[0][0].endswith("...[truncated]")
    assert len(result[0][0]) <= 10 + len("...[truncated]")


def test_field_truncation_bytes():
    """Long bytes values are replaced with description."""
    executor = SQLExecutor(max_field_size=5)
    data = b"123456789"
    rows = [[data]]
    result = executor._truncate_fields(rows)
    assert "binary" in result[0][0]
    assert "truncated" in result[0][0]


def test_field_truncation_dict():
    """Large dict values are serialized and truncated."""
    executor = SQLExecutor(max_field_size=10)
    rows = [[{"key": "a very long value here"}]]
    result = executor._truncate_fields(rows)
    assert isinstance(result[0][0], str)
    assert "...[truncated]" in result[0][0]


def test_field_no_truncation_within_limit():
    """Values within max_field_size are not truncated."""
    executor = SQLExecutor(max_field_size=100)
    rows = [["short"]]
    result = executor._truncate_fields(rows)
    assert result[0][0] == "short"


@pytest.mark.asyncio
async def test_payload_size_trimming():
    """Rows are popped when total payload exceeds max_payload_size."""
    # Create rows where each row adds significant payload
    row_val = "x" * 500  # 500 bytes per row

    mock_rows = []
    for i in range(10):
        r = MagicMock()
        r.values.return_value = [row_val]
        mock_rows.append(r)

    attr = MagicMock()
    attr.name = "data"
    attr.type = MagicMock()
    attr.type.name = "text"

    prepared = MagicMock()
    prepared.get_attributes.return_value = [attr]
    prepared.fetch = AsyncMock(return_value=mock_rows)

    conn = AsyncMock()
    conn.prepare = AsyncMock(return_value=prepared)
    conn.execute = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx)

    # Set max_payload_size very low (1000 bytes) to force trimming
    executor = SQLExecutor(max_payload_size=1000)
    result = await executor.execute_with_connection(conn, "SELECT data", max_rows=10)
    assert result.truncated is True
    assert result.returned_row_count < 10


@pytest.mark.asyncio
async def test_max_rows_override_applied():
    """db_config.max_rows_override limits rows fetched."""
    db_config = DatabaseConfig(database="testdb", max_rows_override=3)
    executor = SQLExecutor(db_config=db_config)

    mock_rows = [MagicMock() for _ in range(5)]
    for r in mock_rows:
        r.values.return_value = ["val"]

    attr = MagicMock()
    attr.name = "col"
    attr.type = MagicMock()
    attr.type.name = "text"

    prepared = MagicMock()
    prepared.get_attributes.return_value = [attr]
    prepared.fetch = AsyncMock(return_value=mock_rows)  # returns 5 rows

    conn = AsyncMock()
    conn.prepare = AsyncMock(return_value=prepared)
    conn.execute = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx)

    # Caller asks for 100 rows, but override caps at 3
    result = await executor.execute_with_connection(conn, "SELECT col", max_rows=100)
    assert result.returned_row_count == 3
    assert result.truncated is True


@pytest.mark.asyncio
async def test_db_config_allowed_schemas_used_in_search_path():
    """Per-db allowed_schemas used for SET LOCAL search_path."""
    db_config = DatabaseConfig(
        database="testdb",
        allowed_schemas=["analytics", "reporting"],
    )
    conn = _make_mock_conn()
    executor = SQLExecutor(allowed_schemas=["public"], db_config=db_config)
    await executor.execute_with_connection(conn, "SELECT 1", max_rows=10)

    execute_calls = [call[0][0] for call in conn.execute.call_args_list]
    search_path_calls = [c for c in execute_calls if "search_path" in c]
    assert search_path_calls
    assert '"analytics"' in search_path_calls[0]
    assert '"reporting"' in search_path_calls[0]
