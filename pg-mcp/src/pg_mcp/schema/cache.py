"""Schema cache with TTL and lazy loading."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from pg_mcp.schema.collector import SchemaCollector
from pg_mcp.schema.models import DatabaseSchema

if TYPE_CHECKING:
    from pg_mcp.db.pool_manager import PoolManager


class CacheEntry:
    """Cached schema with TTL."""

    def __init__(self, schema: DatabaseSchema, ttl: float = 3600.0) -> None:
        self.schema = schema
        self.loaded_at = time.monotonic()
        self.ttl = ttl

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.loaded_at) > self.ttl


class SchemaCache:
    """In-memory schema cache with TTL and lazy load."""

    def __init__(
        self,
        ttl: float = 3600.0,
        max_tables_per_db: int = 500,
        collect_view_definitions: bool = True,
    ) -> None:
        self._summaries: dict[str, dict[str, Any]] = {}
        self._full: dict[str, CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._ttl = ttl
        self._max_tables = max_tables_per_db
        self._collector = SchemaCollector(
            collect_view_definitions=collect_view_definitions
        )

    async def warm_up(self, pool_manager: "PoolManager") -> None:
        """Collect summaries for all databases at startup."""
        for alias, db_pool in pool_manager.pools.items():
            try:
                conn = await db_pool.acquire()
                try:
                    self._summaries[alias] = await self._collector.collect_summary(
                        conn
                    )
                finally:
                    db_pool.release(conn)
            except Exception:
                self._summaries[alias] = {
                    "by_schema": {},
                    "total_tables": 0,
                    "total_views": 0,
                    "table_names": [],
                }

    async def get_or_load(
        self, alias: str, pool_manager: "PoolManager"
    ) -> DatabaseSchema:
        """Lazy load full schema with TTL; refresh when expired."""
        entry = self._full.get(alias)
        if entry and not entry.expired:
            return entry.schema

        lock = self._locks.setdefault(alias, asyncio.Lock())
        async with lock:
            entry = self._full.get(alias)
            if entry and not entry.expired:
                return entry.schema

            db_pool = pool_manager.pools.get(alias)
            if not db_pool:
                raise ValueError(f"Unknown database: {alias}")

            conn = await db_pool.acquire()
            try:
                db_name = await conn.fetchval("SELECT current_database()")
                schema = await self._collector.collect_full(
                    conn, database_name=db_name or alias
                )
            finally:
                db_pool.release(conn)

            if len(schema.tables) > self._max_tables:
                import structlog
                structlog.get_logger().warning(
                    "schema_truncated",
                    db=alias,
                    total=len(schema.tables),
                    limit=self._max_tables,
                )
                schema.tables = schema.tables[: self._max_tables]

            self._full[alias] = CacheEntry(schema, self._ttl)
            return schema

    async def refresh(
        self, alias: str | None, pool_manager: "PoolManager"
    ) -> None:
        """Force refresh cache for alias or all databases."""
        if alias:
            self._full.pop(alias, None)
            await self.get_or_load(alias, pool_manager)
        else:
            for a in list(self._full.keys()):
                self._full.pop(a, None)
            for a in pool_manager.pools:
                await self.get_or_load(a, pool_manager)

    def list_databases(self) -> list[dict[str, Any]]:
        """Return summary list of cached databases."""
        return [{"name": k, **v} for k, v in self._summaries.items()]
