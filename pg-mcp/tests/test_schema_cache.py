"""Unit tests for schema cache."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pg_mcp.schema.cache import CacheEntry, SchemaCache
from pg_mcp.schema.models import DatabaseSchema, TableInfo


def test_cache_entry_not_expired():
    """CacheEntry is not expired within TTL."""
    schema = DatabaseSchema(
        database_name="test",
        schemas=["public"],
        tables=[],
        collected_at="2026-01-01T00:00:00Z",
    )
    entry = CacheEntry(schema, ttl=3600.0)
    assert not entry.expired


def test_cache_entry_expired():
    """CacheEntry expires after TTL."""
    schema = DatabaseSchema(
        database_name="test",
        schemas=["public"],
        tables=[],
        collected_at="2026-01-01T00:00:00Z",
    )
    entry = CacheEntry(schema, ttl=0.001)
    import time
    time.sleep(0.002)
    assert entry.expired


@pytest.mark.asyncio
async def test_get_or_load_lazy_loads():
    """get_or_load loads schema on first call."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value="testdb")
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    mock_pm = MagicMock()
    mock_pm.pools = {"mydb": mock_pool}

    schema = DatabaseSchema(
        database_name="testdb",
        schemas=["public"],
        tables=[TableInfo(schema_name="public", table_name="users", table_type="table")],
        collected_at="2026-01-01T00:00:00Z",
    )

    cache = SchemaCache(ttl=3600.0)
    with patch.object(cache._collector, "collect_full", new=AsyncMock(return_value=schema)):
        result = await cache.get_or_load("mydb", mock_pm)

    assert result.database_name == "testdb"
    assert len(result.tables) == 1
    assert result.tables[0].table_name == "users"
    mock_pool.acquire.assert_called_once()
    mock_pool.release.assert_called_once_with(mock_conn)


@pytest.mark.asyncio
async def test_get_or_load_returns_cached_when_not_expired():
    """get_or_load returns cached schema when not expired."""
    schema = DatabaseSchema(
        database_name="testdb",
        schemas=["public"],
        tables=[],
        collected_at="2026-01-01T00:00:00Z",
    )
    cache = SchemaCache()
    cache._full["mydb"] = CacheEntry(schema, ttl=3600.0)

    mock_pm = MagicMock()
    result = await cache.get_or_load("mydb", mock_pm)

    assert result == schema
    # Cache hit: pool_manager not accessed
    assert not (mock_pm.pools.get.called if hasattr(mock_pm.pools.get, "called") else False)


@pytest.mark.asyncio
async def test_refresh_clears_and_reloads():
    """refresh clears cache and reloads."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value="testdb")
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    mock_pm = MagicMock()
    mock_pm.pools = {"mydb": mock_pool}

    schema = DatabaseSchema(
        database_name="testdb",
        schemas=["public"],
        tables=[],
        collected_at="2026-01-01T00:00:00Z",
    )

    cache = SchemaCache()
    cache._full["mydb"] = CacheEntry(
        DatabaseSchema(
            database_name="old",
            schemas=[],
            tables=[],
            collected_at="2025-01-01T00:00:00Z",
        ),
        ttl=3600.0,
    )

    with patch.object(
        cache._collector,
        "collect_full",
        new=AsyncMock(return_value=schema),
    ):
        await cache.refresh("mydb", mock_pm)

    assert cache._full["mydb"].schema.database_name == "testdb"


def test_list_databases_returns_summaries():
    """list_databases returns summary list."""
    cache = SchemaCache()
    cache._summaries = {
        "db1": {"total_tables": 5, "total_views": 2},
        "db2": {"total_tables": 10, "total_views": 0},
    }

    result = cache.list_databases()
    assert len(result) == 2
    names = [r["name"] for r in result]
    assert "db1" in names
    assert "db2" in names
    assert any(r.get("total_tables") == 5 for r in result)


@pytest.mark.asyncio
async def test_get_or_load_unknown_alias_raises():
    """get_or_load raises for unknown database alias."""
    mock_pm = MagicMock()
    mock_pm.pools = {}

    cache = SchemaCache()

    with pytest.raises(ValueError, match="Unknown database"):
        await cache.get_or_load("unknown", mock_pm)


@pytest.mark.asyncio
async def test_concurrent_load_uses_lock():
    """Concurrent get_or_load for same alias uses lock (no duplicate load)."""
    load_count = 0

    async def mock_collect_full(conn, database_name="unknown"):
        nonlocal load_count
        load_count += 1
        await asyncio.sleep(0.01)  # Simulate slow load
        return DatabaseSchema(
            database_name=database_name,
            schemas=[],
            tables=[],
            collected_at="2026-01-01T00:00:00Z",
        )

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value="testdb")
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    mock_pool.release = AsyncMock()

    mock_pm = MagicMock()
    mock_pm.pools = {"mydb": mock_pool}

    cache = SchemaCache()
    cache._collector.collect_full = mock_collect_full

    # Two concurrent calls - should only load once due to lock
    results = await asyncio.gather(
        cache.get_or_load("mydb", mock_pm),
        cache.get_or_load("mydb", mock_pm),
    )

    assert results[0].database_name == "testdb"
    assert results[1].database_name == "testdb"
    assert load_count == 1
