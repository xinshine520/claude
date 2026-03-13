"""Unit tests for ResultVerifier."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pg_mcp.config import ServerConfig
from pg_mcp.models import ColumnDef, QueryResult
from pg_mcp.verification.verifier import ResultVerifier


@pytest.fixture
def mock_llm():
    """Mock LLMClient."""
    client = AsyncMock()
    return client


def make_verifier(verify_mode: str = "off", verify_sample_rows: int = 5, llm=None):
    """Create ResultVerifier with given config."""
    config = ServerConfig(
        databases="",
        verify_mode=verify_mode,
        verify_sample_rows=verify_sample_rows,
    )
    return ResultVerifier(config, llm or AsyncMock())


def make_result(columns: list[tuple[str, str]], rows: list[list], truncated: bool = False):
    """Create QueryResult for tests."""
    return QueryResult(
        columns=[ColumnDef(name=n, type=t) for n, t in columns],
        rows=rows,
        returned_row_count=len(rows),
        truncated=truncated,
    )


# --- should_verify matrix (6 combos) ---


def test_should_verify_off_false():
    """verify_mode=off + request_verify=False → False."""
    v = make_verifier(verify_mode="off")
    assert v.should_verify(False) is False


def test_should_verify_off_true():
    """verify_mode=off + request_verify=True → False (config overrides)."""
    v = make_verifier(verify_mode="off")
    assert v.should_verify(True) is False


def test_should_verify_metadata_false():
    """verify_mode=metadata + request_verify=False → False."""
    v = make_verifier(verify_mode="metadata")
    assert v.should_verify(False) is False


def test_should_verify_metadata_true():
    """verify_mode=metadata + request_verify=True → True."""
    v = make_verifier(verify_mode="metadata")
    assert v.should_verify(True) is True


def test_should_verify_sample_false():
    """verify_mode=sample + request_verify=False → False."""
    v = make_verifier(verify_mode="sample")
    assert v.should_verify(False) is False


def test_should_verify_sample_true():
    """verify_mode=sample + request_verify=True → True."""
    v = make_verifier(verify_mode="sample")
    assert v.should_verify(True) is True


# --- metadata context format ---


def test_build_metadata_context():
    """Metadata context contains columns, row count, truncated."""
    result = make_result(
        [("id", "int4"), ("name", "text")],
        [["1", "Alice"], ["2", "Bob"]],
        truncated=False,
    )
    v = make_verifier(verify_mode="metadata")
    ctx = v._build_metadata_context(result)
    assert "id(int4)" in ctx
    assert "name(text)" in ctx
    assert "Row count: 2" in ctx
    assert "Truncated: False" in ctx


def test_build_metadata_context_truncated():
    """Truncated metadata is reflected."""
    result = make_result(
        [("x", "int")],
        [[1], [2], [3]],
        truncated=True,
    )
    v = make_verifier(verify_mode="metadata")
    ctx = v._build_metadata_context(result)
    assert "Truncated: True" in ctx


# --- sample context format ---


def test_build_sample_context_respects_verify_sample_rows():
    """Sample context rows limited to verify_sample_rows."""
    result = make_result(
        [("a", "int"), ("b", "text")],
        [[1, "x"], [2, "y"], [3, "z"], [4, "w"], [5, "v"], [6, "u"]],
    )
    v = make_verifier(verify_mode="sample", verify_sample_rows=3)
    ctx = v._build_sample_context(result)
    lines = ctx.split("\n")
    # Header + 3 data rows
    assert len(lines) == 4
    assert "a, b" in lines[0]


def test_build_sample_context_fewer_rows_than_limit():
    """When rows < verify_sample_rows, use all rows."""
    result = make_result(
        [("id", "int")],
        [[1], [2]],
    )
    v = make_verifier(verify_mode="sample", verify_sample_rows=5)
    ctx = v._build_sample_context(result)
    lines = ctx.split("\n")
    assert len(lines) == 3  # header + 2 rows


# --- LLM JSON parse fallback ---


def test_parse_verification_valid_json():
    """Valid JSON returns VerificationResult."""
    v = make_verifier(verify_mode="metadata")
    resp = '{"match": "yes", "explanation": "Correct", "suggested_sql": null}'
    r = v._parse_verification(resp)
    assert r.match == "yes"
    assert r.explanation == "Correct"
    assert r.suggested_sql is None


def test_parse_verification_invalid_json_returns_unknown():
    """Invalid JSON returns match=unknown."""
    v = make_verifier(verify_mode="metadata")
    resp = "This is not JSON at all"
    r = v._parse_verification(resp)
    assert r.match == "unknown"
    assert "parse" in r.explanation.lower() or "could not" in r.explanation.lower()


def test_parse_verification_malformed_json_returns_unknown():
    """Malformed JSON returns match=unknown."""
    v = make_verifier(verify_mode="metadata")
    resp = '{"match": "yes", "explanation": "ok"'  # missing }
    r = v._parse_verification(resp)
    assert r.match == "unknown"


def test_parse_verification_valid_json_in_markdown():
    """JSON inside ```json block is parsed."""
    v = make_verifier(verify_mode="metadata")
    resp = """Here is the result:
```json
{"match": "no", "explanation": "Wrong query", "suggested_sql": "SELECT 2"}
```
"""
    r = v._parse_verification(resp)
    assert r.match == "no"
    assert r.suggested_sql == "SELECT 2"


def test_parse_verification_valid_json_partial():
    """match=partial is accepted."""
    v = make_verifier(verify_mode="metadata")
    resp = '{"match": "partial", "explanation": "Close", "suggested_sql": "SELECT 1"}'
    r = v._parse_verification(resp)
    assert r.match == "partial"


def test_parse_verification_invalid_match_value_returns_unknown():
    """Invalid match value (e.g. "maybe") becomes unknown."""
    v = make_verifier(verify_mode="metadata")
    resp = '{"match": "maybe", "explanation": "Unclear"}'
    r = v._parse_verification(resp)
    assert r.match == "unknown"


@pytest.mark.asyncio
async def test_verify_calls_llm_with_metadata(mock_llm):
    """verify() in metadata mode calls LLM with metadata context."""
    mock_llm.chat = AsyncMock(
        return_value='{"match": "yes", "explanation": "OK", "suggested_sql": null}'
    )
    v = make_verifier(verify_mode="metadata", llm=mock_llm)
    result = make_result([("id", "int")], [[1]])
    r = await v.verify("Count users", "SELECT COUNT(*) FROM users", result)
    assert r.match == "yes"
    mock_llm.chat.assert_called_once()
    call_args = mock_llm.chat.call_args
    assert "Columns:" in call_args.kwargs["user_message"]
    assert "Row count:" in call_args.kwargs["user_message"]


@pytest.mark.asyncio
async def test_verify_calls_llm_with_sample(mock_llm):
    """verify() in sample mode calls LLM with sample rows."""
    mock_llm.chat = AsyncMock(
        return_value='{"match": "yes", "explanation": "OK", "suggested_sql": null}'
    )
    v = make_verifier(verify_mode="sample", verify_sample_rows=2, llm=mock_llm)
    result = make_result(
        [("name", "text")],
        [["Alice"], ["Bob"], ["Carol"]],
    )
    r = await v.verify("List users", "SELECT name FROM users", result)
    assert r.match == "yes"
    call_args = mock_llm.chat.call_args
    assert "name" in call_args.kwargs["user_message"]
    assert "Alice" in call_args.kwargs["user_message"]
    assert "Bob" in call_args.kwargs["user_message"]
    # Carol should not appear (sample limit 2)
    assert "Carol" not in call_args.kwargs["user_message"]
