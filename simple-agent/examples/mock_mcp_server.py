"""
Mock MCP Server for testing

This is a simple MCP server that provides two tools:
- get_time: Get current time
- echo: Echo back the input

Run this server in one terminal, then run example_mcp_real.py
"""

import sys
import json
import asyncio
from datetime import datetime


# MCP Server tools
TOOLS = [
    {
        "name": "get_time",
        "description": "Get the current time",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "Timezone (e.g., UTC, America/New_York)",
                    "default": "UTC",
                },
            },
        },
    },
    {
        "name": "echo",
        "description": "Echo back the input",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to echo",
                },
            },
            "required": ["message"],
        },
    },
]


async def handle_request(request: dict, stdout, stdin) -> dict:
    """Handle a JSON-RPC request."""
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "mock-mcp-server",
                    "version": "1.0.0",
                },
            },
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS},
        }

    elif method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "get_time":
            timezone = args.get("timezone", "UTC")
            now = datetime.now()
            result = {
                "time": now.strftime("%H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
                "timezone": timezone,
            }
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result),
                        }
                    ],
                },
            }

        elif name == "echo":
            message = args.get("message", "")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Echo: {message}",
                        }
                    ],
                },
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }

    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }


async def main():
    """Main server loop."""
    stdout = sys.stdout
    stdin = sys.stdin

    # Send initialize request to set up
    init_request = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {},
    }
    stdout.write(json.dumps(init_request) + "\n")
    stdout.flush()

    # Read and discard init response
    await stdin.readline()

    print("Mock MCP Server started", file=sys.stderr)

    # Process requests
    while True:
        line = await stdin.readline()
        if not line:
            break

        try:
            request = json.loads(line)
            response = await handle_request(request, stdout, stdin)
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            }
            stdout.write(json.dumps(error_response) + "\n")
            stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
