"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import os

import pytest

from pg_mcp.config import ServerConfig

# E2E test database URL (Docker PG from tests/docker-compose.yml)
E2E_PG_URL = os.environ.get(
    "PG_MCP_E2E_DSN",
    "postgresql://postgres:postgres@localhost:5433/pg_mcp_test",
)


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


@pytest.fixture
def e2e_pg_url():
    """PostgreSQL URL for E2E tests (Docker)."""
    return E2E_PG_URL


@pytest.fixture
async def mock_llm_client():
    """Mock LLM client for E2E tests (avoids real API calls)."""
    from unittest.mock import AsyncMock, MagicMock

    from pg_mcp.llm.client import LLMClient

    client = MagicMock(spec=LLMClient)
    client.chat = AsyncMock(return_value="SELECT * FROM users")
    client.extract_sql = MagicMock(return_value="SELECT * FROM users")
    return client


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration (require Docker PostgreSQL)",
    )
    config.addinivalue_line(
        "markers",
        "e2e: marks tests as end-to-end (require Docker PG + seed data)",
    )


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
