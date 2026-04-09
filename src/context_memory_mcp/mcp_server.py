"""FastMCP server for Context Memory MCP.

Provides a stdio-based MCP server with tools for chat memory,
file graph tracking, and context retrieval.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from context_memory_mcp import __version__

# Create the FastMCP server instance
mcp = FastMCP("context-memory-mcp")


@mcp.tool(name="ping", description="Check server status and readiness")
async def ping() -> str:
    """Ping the server to verify it is running and ready.

    Returns:
        JSON string with status, version, and storage readiness.
    """
    return json.dumps({
        "status": "ok",
        "version": __version__,
        "storage": "chromadb-ready",
    })


def run_server() -> None:
    """Run the MCP server on stdio transport.

    This function blocks until the server is stopped.
    FastMCP manages its own event loop — do NOT wrap in asyncio.run().
    """
    mcp.run(transport="stdio")
