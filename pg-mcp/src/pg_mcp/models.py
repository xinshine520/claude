"""Request/response Pydantic models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


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

    model_config = ConfigDict(populate_by_name=True)

    question: str
    database: str | None = None
    return_mode: ReturnMode = ReturnMode.RESULT
    max_rows: int = 100
    verify_result: bool = False


class ColumnDef(BaseModel):
    """Column definition for result metadata."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    type: str


class QueryResult(BaseModel):
    """Query execution result."""

    model_config = ConfigDict(populate_by_name=True)

    columns: list[ColumnDef]
    rows: list[list] = Field(default_factory=list)
    returned_row_count: int = 0
    truncated: bool = False
    total_row_count: int | None = None


class VerificationResult(BaseModel):
    """Semantic verification result from LLM."""

    model_config = ConfigDict(populate_by_name=True)

    match: str  # "yes" | "no" | "partial" | "unknown"
    explanation: str
    suggested_sql: str | None = None


class ErrorDetail(BaseModel):
    """Structured error in response."""

    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str
    stage: str
    retryable: bool


class QueryResponse(BaseModel):
    """Unified query response."""

    model_config = ConfigDict(populate_by_name=True)

    sql: str | None = None
    database: str | None = None
    result: QueryResult | None = None
    verification: VerificationResult | None = None
    error: ErrorDetail | None = None
