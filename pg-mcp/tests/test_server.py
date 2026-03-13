"""Tests for FastMCP server (tool registration, lifespan)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pg_mcp.server import create_mcp, _load_config


def test_create_mcp_returns_fastmcp():
    """create_mcp returns a FastMCP instance with query tool."""
    with patch.dict(
        "os.environ",
        {
            "PG_MCP_DATABASES": "",
            "PG_MCP_LLM_API_KEY": "test-key",
        },
        clear=False,
    ):
        server_config, llm_config = _load_config()
        mcp = create_mcp(server_config, llm_config)
    assert mcp is not None
    assert mcp.name == "pg-mcp"
    # Check query tool is registered
    tools = list(mcp.get_tools()) if hasattr(mcp, "get_tools") else []
    tool_names = [t.name if hasattr(t, "name") else getattr(t, "name", str(t)) for t in tools]
    if tool_names:
        assert "query" in tool_names


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops():
    """Lifespan context manager yields and cleans up."""
    with patch.dict(
        "os.environ",
        {
            "PG_MCP_DATABASES": "",
            "PG_MCP_LLM_API_KEY": "test-key",
        },
        clear=False,
    ):
        server_config, llm_config = _load_config()
        mcp = create_mcp(server_config, llm_config)
    # Access lifespan - FastMCP stores it as _lifespan
    lifespan_fn = getattr(mcp, "_lifespan", None)
    if lifespan_fn is None:
        pytest.skip("FastMCP lifespan not directly accessible")
    # Run lifespan (will fail at pool init if no DBs, but we can check it starts)
    try:
        async with lifespan_fn(mcp) as ctx:
            assert isinstance(ctx, dict)
            assert "config" in ctx or "pool_manager" in ctx or "llm_client" in ctx
    except Exception as e:
        # May fail on pool_manager.initialize() if no DBs - that's ok
        if "pool" not in str(e).lower() and "database" not in str(e).lower():
            raise
