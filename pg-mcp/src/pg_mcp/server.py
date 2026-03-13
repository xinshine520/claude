"""FastMCP server and QueryPipeline orchestration."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Any

import structlog

from pg_mcp.config import (
    LLMConfig,
    ServerConfig,
)
from pg_mcp.db.pool_manager import PoolManager
from pg_mcp.errors import (
    AmbiguousDBError,
    CircuitOpenError,
    ExecutionError,
    LLMError,
    LLMParseError,
    RateLimitError,
    ValidationError,
)
from pg_mcp.llm.client import LLMClient
from pg_mcp.llm.prompts import (
    build_db_selection_prompt,
    build_sql_generation_prompt,
)
from pg_mcp.llm.schema_retriever import SchemaRetriever, render_schema_context
from pg_mcp.logging import configure_logging
from pg_mcp.models import (
    ErrorDetail,
    QueryRequest,
    QueryResponse,
    ReturnMode,
)
from pg_mcp.schema.cache import SchemaCache
from pg_mcp.sql.executor import SQLExecutor
from pg_mcp.sql.validator import SQLValidator
from pg_mcp.verification.verifier import ResultVerifier

logger = structlog.get_logger()

# Map exceptions to (code, message, retryable)
# message=None means use exception's message/code
EXCEPTION_MAP: dict[type[Exception], tuple[str | None, str | None, bool | None]] = {
    CircuitOpenError: ("DB_CIRCUIT_OPEN", "Database temporarily unavailable", True),
    ValidationError: ("VALIDATION_FAILED", None, False),
    ExecutionError: (None, None, None),
    LLMError: ("LLM_ERROR", "AI service unavailable", True),
    LLMParseError: ("LLM_PARSE_ERROR", "Could not generate valid SQL", False),
    RateLimitError: ("RATE_LIMITED", "Too many concurrent queries", True),
    AmbiguousDBError: ("DB_AMBIGUOUS", None, False),
}


def _load_config() -> tuple[ServerConfig, LLMConfig]:
    """Load server and LLM config from environment."""
    server_config = ServerConfig()
    llm_config = LLMConfig()
    return server_config, llm_config


def _create_app_lifespan(server_config: ServerConfig, llm_config: LLMConfig):
    """Create lifespan context manager for FastMCP."""

    @asynccontextmanager
    async def lifespan(_mcp: Any):
        configure_logging(server_config.log_level)
        pool_manager = PoolManager(server_config)
        schema_cache = SchemaCache(
            ttl=server_config.schema_cache_ttl,
            max_tables_per_db=server_config.max_tables_per_db,
            collect_view_definitions=server_config.collect_view_definitions,
        )
        llm_client = LLMClient(
            api_key=llm_config.api_key.get_secret_value(),
            base_url=llm_config.base_url,
            model=llm_config.model,
            max_tokens=llm_config.max_tokens,
            temperature=llm_config.temperature,
            timeout=llm_config.timeout,
        )
        await pool_manager.initialize()
        await schema_cache.warm_up(pool_manager)
        try:
            yield {
                "config": server_config,
                "llm_config": llm_config,
                "pool_manager": pool_manager,
                "schema_cache": schema_cache,
                "llm_client": llm_client,
            }
        finally:
            await pool_manager.close()

    return lifespan


def create_mcp(server_config: ServerConfig, llm_config: LLMConfig) -> Any:
    """Create FastMCP instance with lifespan and query tool."""
    from fastmcp import FastMCP
    from fastmcp.dependencies import CurrentContext
    from fastmcp.server.context import Context

    lifespan = _create_app_lifespan(server_config, llm_config)
    mcp = FastMCP(name="pg-mcp", lifespan=lifespan)

    @mcp.tool(
        name="query",
        description="Query PostgreSQL database using natural language. Returns SQL or query result.",
        exclude_args=["ctx"],  # FastMCP 2.x: keeps ctx out of the tool schema; use Depends() when available
    )
    async def query_tool(
        question: str,
        database: str | None = None,
        return_mode: str = "result",
        max_rows: int = 100,
        verify_result: bool = False,
        ctx: Context = CurrentContext(),
    ) -> dict:
        """MCP tool entry: run full query pipeline."""
        deps = ctx.lifespan_context
        request = QueryRequest(
            question=question,
            database=database,
            return_mode=ReturnMode(return_mode) if return_mode else ReturnMode.RESULT,
            max_rows=max_rows,
            verify_result=verify_result,
        )
        pipeline = QueryPipeline(deps)
        response = await pipeline.execute(request)
        return response.model_dump(exclude_none=True)

    return mcp


class QueryPipeline:
    """Orchestrates the full query flow: DB resolution → schema → SQL gen → validate → execute → verify."""

    MAX_VERIFY_RETRIES = 2

    def __init__(self, deps: dict[str, Any]) -> None:
        self.deps = deps
        self.config: ServerConfig = deps["config"]
        self.pool_manager: PoolManager = deps["pool_manager"]
        self.schema_cache: SchemaCache = deps["schema_cache"]
        self.llm_client: LLMClient = deps["llm_client"]
        self._current_stage = "init"
        self.validator = SQLValidator(
            max_length=self.config.max_sql_length,
            blocked_functions=set(self.config.blocked_functions),
        )
        self.executor = SQLExecutor(
            statement_timeout=self.config.statement_timeout,
            lock_timeout=self.config.lock_timeout,
            max_field_size=self.config.max_field_size,
            max_payload_size=self.config.max_payload_size,
            allowed_schemas=self.config.allowed_schemas,
        )
        self.schema_retriever = SchemaRetriever(max_context_chars=8000)
        self.verifier = ResultVerifier(self.config, self.llm_client)

    async def execute(self, request: QueryRequest) -> QueryResponse:
        """Run the full pipeline. Catches known exceptions and maps to ErrorDetail."""
        try:
            return await self._run(request)
        except tuple(EXCEPTION_MAP.keys()) as e:
            mapping = EXCEPTION_MAP.get(type(e), (None, None, None))
            code, msg, retryable = mapping
            if isinstance(e, ValidationError):
                msg = e.reason
            elif isinstance(e, ExecutionError):
                code = e.code
                msg = e.message
                retryable = e.retryable
            elif isinstance(e, AmbiguousDBError):
                msg = str(e)
            return QueryResponse(
                error=ErrorDetail(
                    code=code or getattr(e, "code", "UNKNOWN"),
                    message=msg or str(e),
                    stage=self._current_stage,
                    retryable=retryable if retryable is not None else getattr(e, "retryable", False),
                )
            )

    async def _run(self, request: QueryRequest) -> QueryResponse:
        self._current_stage = "resolve_database"
        database = await self._resolve_database(request)
        if not database:
            raise AmbiguousDBError("Could not determine database")

        self._current_stage = "ensure_schema_loaded"
        schema = await self.schema_cache.get_or_load(database, self.pool_manager)

        self._current_stage = "generate_sql"
        sql = await self._generate_sql(request.question, schema)

        self._current_stage = "validate_sql"
        self.validator.validate(sql)

        if request.return_mode == ReturnMode.SQL:
            return QueryResponse(sql=sql, database=database)

        self._current_stage = "execute_sql"
        if database not in self.pool_manager.pools:
            raise AmbiguousDBError(f"Database '{database}' not available")
        max_rows = request.max_rows or self.config.default_max_rows
        async with self.pool_manager.connection(database) as conn:
            result = await self.executor.execute_with_connection(
                conn, sql, max_rows
            )

        verification = None
        if self.verifier.should_verify(request.verify_result):
            self._current_stage = "verify_result"
            for attempt in range(self.MAX_VERIFY_RETRIES + 1):
                verification = await self.verifier.verify(
                    request.question, sql, result
                )
                if verification.match == "yes" or attempt == self.MAX_VERIFY_RETRIES:
                    break
                if verification.suggested_sql:
                    sql = verification.suggested_sql
                    self.validator.validate(sql)
                    self._current_stage = "execute_sql"
                    async with self.pool_manager.connection(database) as conn:
                        result = await self.executor.execute_with_connection(
                            conn, sql, max_rows
                        )
                    self._current_stage = "verify_result"
                else:
                    break

        self._current_stage = "build_response"
        return QueryResponse(
            sql=sql,
            database=database,
            result=result,
            verification=verification,
        )

    async def _resolve_database(self, request: QueryRequest) -> str | None:
        if request.database:
            if request.database in self.pool_manager.pools:
                return request.database
            raise AmbiguousDBError(f"Database '{request.database}' not configured")
        if len(self.pool_manager.pools) == 0:
            raise AmbiguousDBError("No databases configured")
        if len(self.pool_manager.pools) == 1:
            return next(iter(self.pool_manager.pools.keys()))
        summaries = self.schema_cache.list_databases()
        matched = self._match_database_local(request.question, summaries)
        if matched:
            return matched
        return await self._match_database_llm(request.question, summaries)

    def _match_database_local(
        self, question: str, summaries: list[dict[str, Any]]
    ) -> str | None:
        """Match database by keyword hit rate on table names. Return alias if unique high score."""
        tokens = re.findall(r"\b\w+\b", question.lower())
        tokens = [t for t in tokens if len(t) > 1]
        if not tokens:
            return None
        scores: list[tuple[float, str]] = []
        for db in summaries:
            alias = db.get("name", "")
            table_names = db.get("table_names", [])
            table_names_lower = [t.lower() for t in table_names]
            searchable = " ".join(table_names_lower)
            score = sum(1.0 for t in tokens if t in searchable)
            for tn_lower in table_names_lower:
                score += sum(2.0 for t in tokens if t in tn_lower)
            if score > 0:
                scores.append((score, alias))
        if not scores:
            return None
        scores.sort(key=lambda x: x[0], reverse=True)
        best_score, best_alias = scores[0]
        if len(scores) > 1 and scores[1][0] >= best_score:
            return None
        return best_alias if best_score > 0 else None

    async def _match_database_llm(
        self, question: str, summaries: list[dict[str, Any]]
    ) -> str:
        """Use LLM to select database. Raises AmbiguousDBError if invalid."""
        if not summaries:
            raise AmbiguousDBError("No databases available")
        db_summaries_str = "\n".join(
            f"- {s.get('name', '')}: {s.get('total_tables', 0)} tables, "
            f"{s.get('total_views', 0)} views"
            for s in summaries
        )
        system, user = build_db_selection_prompt(question, db_summaries_str)
        response = await self.llm_client.chat(
            system_prompt=system,
            user_message=user,
        )
        alias = response.strip().split()[0] if response else ""
        alias = alias.strip(".,;\"'")
        valid = [s.get("name", "") for s in summaries]
        if alias not in valid:
            raise AmbiguousDBError(
                f"LLM selected '{alias}' which is not in configured databases: {valid}"
            )
        return alias

    async def _generate_sql(self, question: str, schema: Any) -> str:
        tables = self.schema_retriever.find_relevant_tables(question, schema)
        schema_ctx = render_schema_context(tables)
        system, user = build_sql_generation_prompt(question, schema_ctx)
        response = await self.llm_client.chat(
            system_prompt=system,
            user_message=user,
        )
        return self.llm_client.extract_sql(response)
