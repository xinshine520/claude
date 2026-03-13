"""Unified error hierarchy and codes."""

from __future__ import annotations


class PgMcpError(Exception):
    """Base exception for pg-mcp."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "PG_MCP_ERROR",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


class ValidationError(PgMcpError):
    """SQL validation failed (syntax, security, etc.)."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason, code=code, retryable=False)
        self.reason = reason


class ExecutionError(PgMcpError):
    """SQL execution failed (timeout, error from PG, etc.)."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message, code=code, retryable=retryable)


class LLMError(PgMcpError):
    """LLM API call failed."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message, code="LLM_ERROR", retryable=retryable)


class LLMParseError(PgMcpError):
    """Failed to extract valid SQL from LLM response."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="LLM_PARSE_ERROR", retryable=False)


class CircuitOpenError(PgMcpError):
    """Database circuit breaker is open."""

    def __init__(self, alias: str) -> None:
        super().__init__(
            f"Database '{alias}' temporarily unavailable",
            code="DB_CIRCUIT_OPEN",
            retryable=True,
        )
        self.alias = alias


class AmbiguousDBError(PgMcpError):
    """Could not uniquely determine which database to use."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="DB_AMBIGUOUS", retryable=False)


class RateLimitError(PgMcpError):
    """Too many concurrent queries."""

    def __init__(self, message: str = "Too many concurrent queries") -> None:
        super().__init__(message, code="RATE_LIMITED", retryable=True)
