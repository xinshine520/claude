"""Request/response Pydantic models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ReturnMode(str, Enum):
    """Whether to return SQL only or execute and return result."""

    SQL = "sql"
    RESULT = "result"


class VerifyMode(str, Enum):
    """Verification mode for query result."""

    OFF = "off"
    METADATA = "metadata"
    SAMPLE = "sample"


class QueryRequest(BaseModel):
    """Natural language query request."""

    question: str
    database: str | None = None
    return_mode: ReturnMode = ReturnMode.RESULT
    max_rows: int = 100
    verify_result: bool = False


class ColumnDef(BaseModel):
    """Column definition for result metadata."""

    name: str
    type: str


class QueryResult(BaseModel):
    """Query execution result."""

    columns: list[ColumnDef]
    rows: list[list] = Field(default_factory=list)
    returned_row_count: int = 0
    truncated: bool = False
    total_row_count: int | None = None


class VerificationResult(BaseModel):
    """Semantic verification result from LLM."""

    match: str  # "yes" | "no" | "partial" | "unknown"
    explanation: str
    suggested_sql: str | None = None


class ErrorDetail(BaseModel):
    """Structured error in response."""

    code: str
    message: str
    stage: str
    retryable: bool


class QueryResponse(BaseModel):
    """Unified query response."""

    sql: str | None = None
    database: str | None = None
    result: QueryResult | None = None
    verification: VerificationResult | None = None
    error: ErrorDetail | None = None
