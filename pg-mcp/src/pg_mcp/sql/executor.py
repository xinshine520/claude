"""Read-only SQL executor with field truncation and error sanitization."""

from __future__ import annotations

import json
import re
from typing import Any

import asyncpg

from pg_mcp.errors import ExecutionError
from pg_mcp.models import ColumnDef, QueryResult


# Allowed schemas for search_path (whitelist)
DEFAULT_ALLOWED_SCHEMAS = ["public"]


class SQLExecutor:
    """Executes validated read-only SQL with timeouts and field truncation."""

    def __init__(
        self,
        statement_timeout: str = "30s",
        lock_timeout: str = "5s",
        max_field_size: int = 10240,
        max_payload_size: int = 5242880,
        allowed_schemas: list[str] | None = None,
    ):
        self.statement_timeout = statement_timeout
        self.lock_timeout = lock_timeout
        self.max_field_size = max_field_size
        self.max_payload_size = max_payload_size
        self._allowed_schemas = allowed_schemas or DEFAULT_ALLOWED_SCHEMAS

    async def execute_with_connection(
        self,
        conn: asyncpg.Connection,
        sql: str,
        max_rows: int,
    ) -> QueryResult:
        """
        Execute SQL using an existing connection. Caller is responsible for
        acquire/release. Use for PoolManager semaphore-aware flow.
        """
        try:
            async with conn.transaction(readonly=True):
                await conn.execute(
                    f"SET LOCAL statement_timeout = '{self.statement_timeout}'"
                )
                await conn.execute(
                    f"SET LOCAL lock_timeout = '{self.lock_timeout}'"
                )
                schemas_str = ", ".join(
                    f'"{s}"' for s in self._allowed_schemas
                )
                await conn.execute(f"SET LOCAL search_path = {schemas_str}")

                prepared = await conn.prepare(sql)
                attrs = prepared.get_attributes()

                columns = [
                    ColumnDef(
                        name=attr.name,
                        type=getattr(attr.type, "name", "text") or "text",
                    )
                    for attr in attrs
                ]

                rows = await prepared.fetch(max_rows + 1)
                truncated = len(rows) > max_rows
                if truncated:
                    rows = rows[:max_rows]

                result_rows = [list(r.values()) for r in rows]
                result_rows = self._truncate_fields(result_rows)

                while (
                    result_rows
                    and self._estimate_payload_size(result_rows)
                    > self.max_payload_size
                ):
                    result_rows.pop()
                    truncated = True

                return QueryResult(
                    columns=columns,
                    rows=result_rows,
                    returned_row_count=len(result_rows),
                    truncated=truncated,
                    total_row_count=None,
                )
        except asyncpg.QueryCanceledError:
            raise ExecutionError(
                "EXECUTION_TIMEOUT",
                "Query timed out",
                retryable=False,
            )
        except asyncpg.PostgresError as e:
            raise ExecutionError(
                "EXECUTION_ERROR",
                self._sanitize_error(e),
                retryable=False,
            )

    async def execute_readonly(
        self,
        pool: Any,  # DatabasePool from db.pool_manager
        sql: str,
        max_rows: int,
    ) -> QueryResult:
        """
        Execute SQL in a read-only transaction. Uses prepare() + fetch for
        row limit; get_attributes() for column metadata (works with empty result).
        """
        conn = await pool.acquire()
        try:
            return await self.execute_with_connection(conn, sql, max_rows)
        finally:
            await pool.release(conn)

    def _truncate_fields(self, rows: list[list]) -> list[list]:
        """Truncate oversized field values."""
        max_size = self.max_field_size
        for row in rows:
            for i, val in enumerate(row):
                if isinstance(val, str) and len(val) > max_size:
                    row[i] = val[:max_size] + "...[truncated]"
                elif isinstance(val, bytes) and len(val) > max_size:
                    row[i] = f"<binary {len(val)} bytes, truncated>"
                elif isinstance(val, (dict, list)):
                    serialized = json.dumps(val, default=str)
                    if len(serialized) > max_size:
                        row[i] = serialized[:max_size] + "...[truncated]"
        return rows

    def _estimate_payload_size(self, rows: list[list]) -> int:
        return sum(
            len(str(v)) for row in rows for v in row
        )

    def _sanitize_error(self, exc: asyncpg.PostgresError) -> str:
        """Redact identifiers and internal details from error messages."""
        msg = str(exc)
        msg = re.sub(
            r"(relation|table|column|function|schema|type)\s+\"[^\"]*\"",
            r'\1 "[redacted]"',
            msg,
        )
        msg = re.sub(r"DETAIL:.*", "DETAIL: [redacted]", msg, flags=re.DOTALL)
        msg = re.sub(r"HINT:.*", "HINT: [redacted]", msg, flags=re.DOTALL)
        msg = re.sub(r"CONTEXT:.*", "CONTEXT: [redacted]", msg, flags=re.DOTALL)
        msg = re.sub(r"LINE \d+:.*", "", msg, flags=re.DOTALL)
        return msg.strip()
