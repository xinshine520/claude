"""Entry point for python -m pg_mcp."""

from __future__ import annotations

import argparse


def main() -> None:
    """Parse args and run MCP server."""
    parser = argparse.ArgumentParser(
        prog="pg_mcp",
        description="Natural language PostgreSQL query MCP server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="Port for SSE/HTTP transport (default: 8000)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for SSE/HTTP transport (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    from pg_mcp.server import _load_config, create_mcp

    server_config, llm_config = _load_config()
    mcp = create_mcp(server_config, llm_config)

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(
            transport=args.transport,
            port=args.port,
            host=args.host,
        )


if __name__ == "__main__":
    main()
