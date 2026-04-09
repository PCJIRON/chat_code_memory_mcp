"""FastMCP server for Context Memory MCP.

Provides a stdio-based MCP server with tools for chat memory,
file graph tracking, and context retrieval.

Tool Registration Pattern (Option B):
Each domain module exposes a `register(mcp: FastMCP)` function.
This file collects all registrations and calls them at startup.
This keeps tool definitions co-located with domain logic and avoids circular imports.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from context_memory_mcp import __version__

# Create the FastMCP server instance
mcp = FastMCP("context-memory-mcp")


def _register_core(mcp: FastMCP) -> None:
    """Register core tools (ping, health, etc.)."""

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


def register_all() -> None:
    """Register all MCP tools from domain modules.

    Each domain module exposes a `register(mcp: FastMCP)` function.
    Call this function at server startup to register all tools.
    """
    _register_core(mcp)
    # Phase 2
    from context_memory_mcp.chat_store import register as register_chat

    register_chat(mcp)
    # Phase 3
    from context_memory_mcp.file_graph import register as register_graph

    register_graph(mcp)
    # Phase 4: from context_memory_mcp.context import register as register_context
    # register_context(mcp)


def run_server() -> None:
    """Run the MCP server on stdio transport.

    This function blocks until the server is stopped.
    FastMCP manages its own event loop — do NOT wrap in asyncio.run().
    """
    register_all()
    mcp.run(transport="stdio")
