"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import pytest

from pg_mcp.config import ServerConfig


@pytest.fixture
def server_config():
    """Default ServerConfig for tests."""
    return ServerConfig(
        databases="",
        statement_timeout="30s",
        lock_timeout="5s",
        default_max_rows=100,
        max_field_size=10240,
        max_payload_size=5242880,
        pool_size_per_db=2,
        max_concurrent_queries=10,
        verify_mode="off",
        max_sql_length=10000,
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration (require Docker PostgreSQL)",
    )


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
