"""Unit tests for circuit breaker state machine."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pg_mcp.db.pool_manager import (
    CIRCUIT_TRIPPING_ERRORS,
    CircuitState,
    DatabasePool,
)
from pydantic import SecretStr

from pg_mcp.config import DatabaseConfig, ServerConfig
from pg_mcp.errors import CircuitOpenError


@pytest.fixture
def server_config():
    return ServerConfig(
        databases="",
        pool_size_per_db=2,
        max_concurrent_queries=10,
    )


@pytest.fixture
def db_config():
    return DatabaseConfig(
        host="localhost",
        port=5432,
        database="test",
        user="test",
        password=SecretStr("test"),
    )


@pytest.fixture
def pool(db_config, server_config):
    return DatabasePool("testdb", db_config, server_config)


@pytest.mark.asyncio
async def test_closed_state_normal_acquire(pool):
    """CLOSED: Normal acquire succeeds."""
    mock_pool = AsyncMock()
    mock_conn = MagicMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    pool.pool = mock_pool

    conn = await pool.acquire()
    assert conn == mock_conn
    assert pool.circuit_state == CircuitState.CLOSED
    assert pool.failure_count == 0


@pytest.mark.asyncio
async def test_closed_to_open_after_failures(pool):
    """CLOSED -> OPEN after failure_threshold consecutive failures."""
    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(side_effect=asyncio.TimeoutError())
    pool.pool = mock_pool
    pool.failure_threshold = 3

    for _ in range(3):
        with pytest.raises(asyncio.TimeoutError):
            await pool.acquire()

    assert pool.circuit_state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        pool._check_circuit()


@pytest.mark.asyncio
async def test_open_rejects_immediately(pool):
    """OPEN: Rejects requests immediately before recovery_timeout."""
    pool.circuit_state = CircuitState.OPEN
    pool.last_failure_time = __import__("time").monotonic()
    pool.recovery_timeout = 60.0

    with pytest.raises(CircuitOpenError):
        await pool.acquire()


@pytest.mark.asyncio
async def test_open_transitions_to_half_open_after_timeout(pool):
    """OPEN -> HALF_OPEN after recovery_timeout."""
    pool.circuit_state = CircuitState.OPEN
    pool.last_failure_time = __import__("time").monotonic() - 61
    pool.recovery_timeout = 60.0

    mock_pool = AsyncMock()
    mock_conn = MagicMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    pool.pool = mock_pool

    conn = await pool.acquire()
    assert conn == mock_conn
    assert pool.circuit_state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_probe_success_closes_circuit(pool):
    """HALF_OPEN + probe success -> CLOSED."""
    pool.circuit_state = CircuitState.HALF_OPEN
    pool.last_failure_time = __import__("time").monotonic() - 61
    pool.recovery_timeout = 60.0

    mock_pool = AsyncMock()
    mock_conn = MagicMock()
    mock_pool.acquire = AsyncMock(return_value=mock_conn)
    pool.pool = mock_pool

    conn = await pool.acquire()
    assert conn == mock_conn
    assert pool.circuit_state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_probe_failure_opens_again(pool):
    """HALF_OPEN + probe failure -> OPEN (reset timer)."""
    pool.circuit_state = CircuitState.HALF_OPEN
    pool.last_failure_time = __import__("time").monotonic() - 61
    pool.recovery_timeout = 60.0

    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(side_effect=ConnectionError())
    pool.pool = mock_pool

    with pytest.raises(ConnectionError):
        await pool.acquire()

    assert pool.circuit_state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_non_tripping_error_does_not_increment_count(pool):
    """Non-circuit-tripping errors (e.g. PostgresSyntaxError) do not affect failure count."""
    import asyncpg

    mock_pool = AsyncMock()
    mock_pool.acquire = AsyncMock(side_effect=asyncpg.PostgresSyntaxError("syntax error"))
    pool.pool = mock_pool

    with pytest.raises(asyncpg.PostgresSyntaxError):
        await pool.acquire()

    # Failure count should not have increased (PostgresSyntaxError is not in CIRCUIT_TRIPPING_ERRORS)
    assert pool.failure_count == 0


def test_circuit_tripping_errors_defined():
    """CIRCUIT_TRIPPING_ERRORS includes expected types."""
    import asyncpg

    assert asyncio.TimeoutError in CIRCUIT_TRIPPING_ERRORS
    assert asyncpg.InterfaceError in CIRCUIT_TRIPPING_ERRORS
    assert asyncpg.InternalServerError in CIRCUIT_TRIPPING_ERRORS
    assert ConnectionError in CIRCUIT_TRIPPING_ERRORS
    assert OSError in CIRCUIT_TRIPPING_ERRORS
