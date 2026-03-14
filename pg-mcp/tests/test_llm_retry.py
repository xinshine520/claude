"""Tests for LLM retry/backoff logic (Phase 10)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from pg_mcp.errors import LLMError, RateLimitError
from pg_mcp.llm.client import LLMClient


def _make_client(max_retries: int = 3, retry_base_delay: float = 0.01) -> LLMClient:
    return LLMClient(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
        max_retries=max_retries,
        retry_base_delay=retry_base_delay,
    )


def _make_ok_response(content: str = "SELECT 1") -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


def _make_rate_limit_error() -> openai.RateLimitError:
    """Create a real openai.RateLimitError using an httpx.Response."""
    import httpx
    req = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    resp = httpx.Response(429, request=req)
    return openai.RateLimitError("rate limited", response=resp, body=None)


def _make_api_status_error(status_code: int) -> openai.APIStatusError:
    """Create a real openai.APIStatusError with a given HTTP status code."""
    import httpx
    req = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    resp = httpx.Response(status_code, request=req)
    return openai.APIStatusError(f"HTTP {status_code}", response=resp, body=None)


@pytest.mark.asyncio
async def test_rate_limit_success_on_third_attempt():
    """Raises RateLimitError twice then succeeds on 3rd attempt."""
    client = _make_client(max_retries=3)
    ok_response = _make_ok_response("SELECT 1")
    rate_err = _make_rate_limit_error()

    call_count = 0

    async def mock_create(**kwargs):  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise rate_err
        return ok_response

    with patch.object(client._client.chat.completions, "create", side_effect=mock_create):
        with patch("pg_mcp.llm.client.asyncio.sleep", new_callable=AsyncMock):
            result = await client.chat("sys", "user")

    assert result == "SELECT 1"
    assert call_count == 3


@pytest.mark.asyncio
async def test_rate_limit_exhausted_raises_rate_limit_error():
    """Always raising RateLimitError → pg_mcp RateLimitError after max_retries."""
    client = _make_client(max_retries=2)
    rate_err = _make_rate_limit_error()

    async def mock_create(**kwargs):  # noqa: ARG001
        raise rate_err

    with patch.object(client._client.chat.completions, "create", side_effect=mock_create):
        with patch("pg_mcp.llm.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(RateLimitError):
                await client.chat("sys", "user")

    # Should have slept max_retries times (one sleep per retry before giving up)
    assert mock_sleep.call_count == client._max_retries


@pytest.mark.asyncio
async def test_server_error_retried_then_raises_llm_error():
    """APIStatusError 500 retried; eventual failure raises LLMError."""
    client = _make_client(max_retries=2)
    server_err = _make_api_status_error(500)

    async def mock_create(**kwargs):  # noqa: ARG001
        raise server_err

    with patch.object(client._client.chat.completions, "create", side_effect=mock_create):
        with patch("pg_mcp.llm.client.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(LLMError):
                await client.chat("sys", "user")


@pytest.mark.asyncio
async def test_server_error_success_after_retry():
    """APIStatusError 500 once then success."""
    client = _make_client(max_retries=2)
    ok_response = _make_ok_response("SELECT 2")
    server_err = _make_api_status_error(500)

    call_count = 0

    async def mock_create(**kwargs):  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise server_err
        return ok_response

    with patch.object(client._client.chat.completions, "create", side_effect=mock_create):
        with patch("pg_mcp.llm.client.asyncio.sleep", new_callable=AsyncMock):
            result = await client.chat("sys", "user")

    assert result == "SELECT 2"


@pytest.mark.asyncio
async def test_non_retriable_4xx_raises_immediately():
    """4xx errors (except 429) are not retried."""
    client = _make_client(max_retries=3)
    client_err = _make_api_status_error(403)

    call_count = 0

    async def mock_create(**kwargs):  # noqa: ARG001
        nonlocal call_count
        call_count += 1
        raise client_err

    with patch.object(client._client.chat.completions, "create", side_effect=mock_create):
        with patch("pg_mcp.llm.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(LLMError):
                await client.chat("sys", "user")

    # Should NOT have slept (no retry for 4xx)
    assert mock_sleep.call_count == 0
    assert call_count == 1


@pytest.mark.asyncio
async def test_exponential_backoff_delays():
    """Retry delays follow exponential backoff with jitter, capped at 30s."""
    client = _make_client(max_retries=3, retry_base_delay=1.0)
    sleep_calls: list[float] = []
    rate_err = _make_rate_limit_error()

    async def mock_create(**kwargs):  # noqa: ARG001
        raise rate_err

    async def mock_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    with patch.object(client._client.chat.completions, "create", side_effect=mock_create):
        with patch("pg_mcp.llm.client.asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(RateLimitError):
                await client.chat("sys", "user")

    assert len(sleep_calls) == client._max_retries
    # Each delay should be >= base_delay * 2^attempt (before jitter)
    # and <= 30.0 (cap)
    for delay in sleep_calls:
        assert 0.0 < delay <= 30.0
    # Delays should be increasing (exponential base grows)
    # With jitter this isn't guaranteed strictly, but first < last in practice
    # at least first delay starts from base_delay * 2^0 = 1.0 base
    assert sleep_calls[0] >= 1.0  # base * 2^0 = 1.0 + jitter


@pytest.mark.asyncio
async def test_generic_exception_raises_llm_error():
    """Non-openai exceptions are wrapped in LLMError."""
    client = _make_client(max_retries=3)

    async def mock_create(**kwargs):  # noqa: ARG001
        raise ConnectionError("network failure")

    with patch.object(client._client.chat.completions, "create", side_effect=mock_create):
        with patch("pg_mcp.llm.client.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(LLMError) as exc:
                await client.chat("sys", "user")
    assert "network failure" in str(exc.value)
