"""Integration tests for QueryPipeline (mock LLM + mock PG)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pg_mcp.models import QueryRequest, ReturnMode
from pg_mcp.server import QueryPipeline


def make_deps(
    mock_llm=None,
    mock_pool_manager=None,
    mock_schema_cache=None,
    mock_config=None,
):
    """Build deps dict for QueryPipeline."""
    config = mock_config or MagicMock()
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

    pool_manager = mock_pool_manager or MagicMock()
    schema_cache = mock_schema_cache or MagicMock()
    llm_client = mock_llm or MagicMock()

    return {
        "config": config,
        "pool_manager": pool_manager,
        "schema_cache": schema_cache,
        "llm_client": llm_client,
    }


@pytest.fixture
def mock_llm():
    """LLM that returns simple SELECT."""
    client = AsyncMock()
    client.chat = AsyncMock(return_value="SELECT * FROM users")
    client.extract_sql = MagicMock(return_value="SELECT * FROM users")
    return client


@pytest.fixture
def mock_schema():
    """Minimal schema for tests."""
    from pg_mcp.schema.models import ColumnInfo, DatabaseSchema, TableInfo

    return DatabaseSchema(
        database_name="testdb",
        schemas=["public"],
        tables=[
            TableInfo(
                schema_name="public",
                table_name="users",
                table_type="table",
                columns=[
                    ColumnInfo(name="id", type="int4", nullable=False),
                    ColumnInfo(name="name", type="text", nullable=True),
                ],
            )
        ],
        collected_at="2024-01-01T00:00:00Z",
    )


@pytest.fixture
def mock_pool_manager():
    """Pool manager with mock connection."""
    from contextlib import asynccontextmanager

    pm = MagicMock()
    attr_id = MagicMock()
    attr_id.name = "id"
    attr_id.type = MagicMock()
    attr_id.type.name = "int4"
    attr_name = MagicMock()
    attr_name.name = "name"
    attr_name.type = MagicMock()
    attr_name.type.name = "text"
    prepared = MagicMock()
    prepared.get_attributes.return_value = [attr_id, attr_name]
    prepared.fetch = AsyncMock(return_value=[])

    conn = AsyncMock()
    conn.prepare = AsyncMock(return_value=prepared)
    conn.execute = AsyncMock()
    tx_ctx = MagicMock()
    tx_ctx.__aenter__ = AsyncMock(return_value=tx_ctx)
    tx_ctx.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_ctx)

    pm.pools = {"mydb": MagicMock()}
    pm.acquire = AsyncMock(return_value=conn)
    pm.release = AsyncMock()

    @asynccontextmanager
    async def _connection(alias):
        yield conn

    pm.connection = _connection
    return pm


@pytest.fixture
def mock_schema_cache(mock_schema):
    """Schema cache that returns mock schema."""
    cache = MagicMock()
    cache.get_or_load = AsyncMock(return_value=mock_schema)
    cache.list_databases = MagicMock(return_value=[
        {"name": "mydb", "total_tables": 1, "total_views": 0, "table_names": ["public.users"]}
    ])
    return cache


@pytest.mark.asyncio
async def test_pipeline_sql_mode(mock_llm, mock_schema_cache, mock_config=None):
    """SQL mode returns SQL without executing."""
    pm = MagicMock()
    pm.pools = {"mydb": MagicMock()}
    deps = make_deps(
        mock_llm=mock_llm,
        mock_pool_manager=pm,
        mock_schema_cache=mock_schema_cache,
    )
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="List users",
        database="mydb",
        return_mode=ReturnMode.SQL,
    )
    response = await pipeline.execute(request)
    assert response.sql == "SELECT * FROM users"
    assert response.database == "mydb"
    assert response.result is None
    assert response.error is None
    pm.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_result_mode(
    mock_llm, mock_schema_cache, mock_pool_manager
):
    """Result mode executes and returns result."""
    deps = make_deps(
        mock_llm=mock_llm,
        mock_pool_manager=mock_pool_manager,
        mock_schema_cache=mock_schema_cache,
    )
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="List users",
        database="mydb",
        return_mode=ReturnMode.RESULT,
    )
    response = await pipeline.execute(request)
    assert response.sql == "SELECT * FROM users"
    assert response.database == "mydb"
    assert response.result is not None
    assert response.error is None


@pytest.mark.asyncio
async def test_pipeline_db_inference_single_db(mock_llm, mock_schema_cache):
    """Single DB: infer database without explicit param."""
    pm = MagicMock()
    pm.pools = {"mydb": MagicMock()}
    pm.acquire = AsyncMock(return_value=MagicMock(
        prepare=AsyncMock(return_value=MagicMock(
            get_attributes=MagicMock(return_value=[
                MagicMock(name="id", type=MagicMock(name="int4")),
            ]),
            fetch=AsyncMock(return_value=[]),
        )),
        transaction=MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(),
            __aexit__=AsyncMock(return_value=None),
        )),
    ))
    pm.release = MagicMock()
    deps = make_deps(
        mock_llm=mock_llm,
        mock_pool_manager=pm,
        mock_schema_cache=mock_schema_cache,
    )
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="List users",
        database=None,
        return_mode=ReturnMode.SQL,
    )
    response = await pipeline.execute(request)
    assert response.database == "mydb"


@pytest.mark.asyncio
async def test_pipeline_validation_failure(mock_schema_cache):
    """Dangerous SQL returns VALIDATION_FAILED error."""
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value="SELECT pg_sleep(100)")
    llm.extract_sql = MagicMock(return_value="SELECT pg_sleep(100)")
    pm = MagicMock()
    pm.pools = {"mydb": MagicMock()}
    deps = make_deps(
        mock_llm=llm,
        mock_pool_manager=pm,
        mock_schema_cache=mock_schema_cache,
    )
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="Sleep",
        database="mydb",
        return_mode=ReturnMode.RESULT,
    )
    response = await pipeline.execute(request)
    assert response.error is not None
    assert response.error.code == "VALIDATION_FAILED"
    assert response.result is None


@pytest.mark.asyncio
async def test_pipeline_llm_error(mock_schema_cache):
    """LLM error returns LLM_ERROR."""
    from pg_mcp.errors import LLMError

    llm = AsyncMock()
    llm.chat = AsyncMock(side_effect=LLMError("API failed", retryable=True))
    llm.extract_sql = MagicMock()
    pm = MagicMock()
    pm.pools = {"mydb": MagicMock()}
    deps = make_deps(
        mock_llm=llm,
        mock_pool_manager=pm,
        mock_schema_cache=mock_schema_cache,
    )
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="List users",
        database="mydb",
        return_mode=ReturnMode.SQL,
    )
    response = await pipeline.execute(request)
    assert response.error is not None
    assert response.error.code == "LLM_ERROR"
    assert response.error.retryable is True


@pytest.mark.asyncio
async def test_pipeline_unknown_database(mock_llm, mock_schema_cache):
    """Unknown database raises AmbiguousDBError."""
    pm = MagicMock()
    pm.pools = {"mydb": MagicMock()}
    deps = make_deps(
        mock_llm=mock_llm,
        mock_pool_manager=pm,
        mock_schema_cache=mock_schema_cache,
    )
    pipeline = QueryPipeline(deps)
    request = QueryRequest(
        question="List users",
        database="nonexistent",
        return_mode=ReturnMode.SQL,
    )
    response = await pipeline.execute(request)
    assert response.error is not None
    assert "nonexistent" in response.error.message.lower() or "not" in response.error.message.lower()
