"""Database connection pool management with circuit breaker."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import asyncpg

from pg_mcp.config import DatabaseConfig, ServerConfig, parse_databases_config
from pg_mcp.errors import CircuitOpenError


class CircuitState:
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal: all requests pass
    OPEN = "open"  # Tripped: reject all requests
    HALF_OPEN = "half_open"  # Probing: allow single request to test recovery


# Errors that count toward circuit tripping
CIRCUIT_TRIPPING_ERRORS = (
    asyncio.TimeoutError,
    asyncpg.InterfaceError,
    asyncpg.InternalServerError,
    ConnectionError,
    OSError,
)


class DatabasePool:
    """
    Per-database connection pool with circuit breaker.

    State transitions:
      CLOSED --[consecutive failures >= threshold]--> OPEN
      OPEN   --[wait recovery_timeout]--> HALF_OPEN
      HALF_OPEN --[probe success]--> CLOSED
      HALF_OPEN --[probe failure]--> OPEN (reset timer)
    """

    def __init__(
        self,
        alias: str,
        db_config: DatabaseConfig,
        server_config: ServerConfig,
    ) -> None:
        self.alias = alias
        self.db_config = db_config
        self.server_config = server_config
        self.pool: asyncpg.Pool | None = None
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = 5
        self.recovery_timeout = 60.0
        self.last_failure_time = 0.0
        self._half_open_lock = asyncio.Lock()

    def _build_dsn(self) -> str:
        if self.db_config.url:
            return self.db_config.url
        pw = self.db_config.password.get_secret_value()
        host = self.db_config.host
        port = self.db_config.port
        db = self.db_config.database
        user = self.db_config.user
        ssl = self.db_config.sslmode
        return f"postgresql://{user}:{pw}@{host}:{port}/{db}?sslmode={ssl}"

    async def create_pool(self) -> None:
        dsn = self._build_dsn()
        self.pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=self.server_config.pool_size_per_db,
            max_inactive_connection_lifetime=300.0,
            command_timeout=60,
        )

    def _check_circuit(self) -> None:
        if self.circuit_state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                self.circuit_state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError(self.alias)
        if self.circuit_state == CircuitState.HALF_OPEN:
            if self._half_open_lock.locked():
                raise CircuitOpenError(self.alias)

    def _on_success(self) -> None:
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0

    def _on_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.circuit_state == CircuitState.HALF_OPEN:
            self.circuit_state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            self.circuit_state = CircuitState.OPEN

    async def acquire(self) -> asyncpg.Connection:
        self._check_circuit()
        if self.pool is None:
            raise CircuitOpenError(self.alias)

        async def _do_acquire() -> asyncpg.Connection:
            conn = await asyncio.wait_for(self.pool.acquire(), timeout=10.0)
            self._on_success()
            return conn

        try:
            if self.circuit_state == CircuitState.HALF_OPEN:
                async with self._half_open_lock:
                    return await _do_acquire()
            return await _do_acquire()
        except CIRCUIT_TRIPPING_ERRORS:
            self._on_failure()
            raise

    def release(self, conn: asyncpg.Connection) -> None:
        if self.pool:
            self.pool.release(conn)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None


class PoolManager:
    """Manages database pools with global concurrency limit."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.pools: dict[str, DatabasePool] = {}
        self._semaphore = asyncio.Semaphore(config.max_concurrent_queries)

    async def initialize(self) -> None:
        """Create pools for all configured databases."""
        db_configs = parse_databases_config(self.config)
        for alias, db_config in db_configs.items():
            try:
                pool = DatabasePool(alias, db_config, self.config)
                await pool.create_pool()
                self.pools[alias] = pool
            except Exception as e:
                # Log and skip failed databases
                import structlog
                structlog.get_logger().error(
                    "pool_create_failed", db=alias, error=str(e)
                )

    async def acquire(self, alias: str) -> asyncpg.Connection:
        """Acquire connection with semaphore and circuit check."""
        async with self._semaphore:
            if alias not in self.pools:
                raise ValueError(f"Unknown database: {alias}")
            return await self.pools[alias].acquire()

    def release(self, alias: str, conn: asyncpg.Connection) -> None:
        if alias in self.pools:
            self.pools[alias].release(conn)

    async def close(self) -> None:
        for pool in self.pools.values():
            await pool.close()
        self.pools.clear()
