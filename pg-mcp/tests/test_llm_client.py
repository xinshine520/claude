"""Unit tests for LLM client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pg_mcp.errors import LLMError, LLMParseError
from pg_mcp.llm.client import LLMClient


@pytest.fixture
def client():
    return LLMClient(
        api_key="test-key",
        base_url="https://api.example.com",
        model="test-model",
    )


@pytest.mark.asyncio
async def test_chat_returns_content(client):
    """Normal response returns stripped content."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "  SELECT * FROM users  "

    with patch.object(
        client._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await client.chat("system", "user")
        assert result == "SELECT * FROM users"


@pytest.mark.asyncio
async def test_chat_api_error_raises_llm_error(client):
    """API errors raise LLMError."""
    with patch.object(
        client._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        side_effect=Exception("API rate limit"),
    ):
        with pytest.raises(LLMError) as exc:
            await client.chat("system", "user")
        assert "rate limit" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_chat_empty_choices_raises_parse_error(client):
    """Empty choices raise LLMParseError."""
    mock_response = MagicMock()
    mock_response.choices = []

    with patch.object(
        client._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        with pytest.raises(LLMParseError) as exc:
            await client.chat("system", "user")
        assert "empty" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_chat_none_content_raises_parse_error(client):
    """None content raises LLMParseError."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = None

    with patch.object(
        client._client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        with pytest.raises(LLMParseError) as exc:
            await client.chat("system", "user")
        assert "content" in str(exc.value).lower()


def test_extract_sql_from_markdown_block(client):
    """Extract SQL from ```sql...``` block."""
    response = """Here is the query:

```sql
SELECT * FROM users WHERE id = 1
```
"""
    sql = client.extract_sql(response)
    assert sql == "SELECT * FROM users WHERE id = 1"


def test_extract_sql_full_text_when_no_block(client):
    """When no markdown block, use full text as SQL."""
    response = "SELECT * FROM orders"
    sql = client.extract_sql(response)
    assert sql == "SELECT * FROM orders"


def test_extract_sql_empty_response_raises(client):
    """Empty response raises LLMParseError."""
    with pytest.raises(LLMParseError) as exc:
        client.extract_sql("")
    assert "empty" in str(exc.value).lower() or "extract" in str(exc.value).lower()


def test_extract_sql_whitespace_only_block_raises(client):
    """Code block with only whitespace raises LLMParseError."""
    response = "```sql\n   \n```"
    with pytest.raises(LLMParseError):
        client.extract_sql(response)
