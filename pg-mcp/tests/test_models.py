"""Tests for Pydantic models."""

from __future__ import annotations


from pg_mcp.models import (
    ColumnDef,
    ErrorDetail,
    QueryRequest,
    QueryResponse,
    QueryResult,
    ReturnMode,
    VerificationResult,
    VerifyMode,
)


def test_query_request_defaults():
    """QueryRequest has expected defaults."""
    req = QueryRequest(question="How many users?")
    assert req.database is None
    assert req.return_mode == ReturnMode.RESULT
    assert req.max_rows == 100
    assert req.verify_result is False


def test_query_request_return_mode_sql():
    """QueryRequest accepts return_mode=sql."""
    req = QueryRequest(question="x", return_mode=ReturnMode.SQL)
    assert req.return_mode == ReturnMode.SQL


def test_column_def():
    """ColumnDef serialization."""
    c = ColumnDef(name="id", type="int4")
    assert c.name == "id"
    assert c.type == "int4"
    assert c.model_dump() == {"name": "id", "type": "int4"}


def test_query_result():
    """QueryResult model."""
    result = QueryResult(
        columns=[ColumnDef(name="x", type="text")],
        rows=[[1], [2]],
        returned_row_count=2,
        truncated=False,
    )
    assert len(result.columns) == 1
    assert len(result.rows) == 2
    assert result.returned_row_count == 2


def test_verification_result():
    """VerificationResult model."""
    v = VerificationResult(match="yes", explanation="Correct")
    assert v.match == "yes"
    assert v.suggested_sql is None
    v2 = VerificationResult(match="no", explanation="Wrong", suggested_sql="SELECT 2")
    assert v2.suggested_sql == "SELECT 2"


def test_error_detail():
    """ErrorDetail model."""
    e = ErrorDetail(
        code="VALIDATION_FAILED",
        message="Invalid SQL",
        stage="validate_sql",
        retryable=False,
    )
    assert e.code == "VALIDATION_FAILED"
    assert e.retryable is False


def test_query_response_with_result():
    """QueryResponse with result."""
    result = QueryResult(
        columns=[ColumnDef(name="n", type="int4")],
        rows=[[1]],
        returned_row_count=1,
        truncated=False,
    )
    resp = QueryResponse(sql="SELECT 1", database="mydb", result=result)
    assert resp.result is not None
    assert resp.error is None
    d = resp.model_dump(exclude_none=True)
    assert "sql" in d
    assert "result" in d
    assert "error" not in d


def test_query_response_with_error():
    """QueryResponse with error."""
    err = ErrorDetail(
        code="DB_UNAVAILABLE",
        message="Connection failed",
        stage="execute_sql",
        retryable=True,
    )
    resp = QueryResponse(error=err)
    assert resp.error is not None
    assert resp.error.code == "DB_UNAVAILABLE"


def test_verify_mode_enum():
    """VerifyMode enum values."""
    assert VerifyMode.OFF.value == "off"
    assert VerifyMode.METADATA.value == "metadata"
    assert VerifyMode.SAMPLE.value == "sample"
