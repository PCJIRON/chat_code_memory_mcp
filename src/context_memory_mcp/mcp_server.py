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
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from context_memory_mcp import __version__

# Create the FastMCP server instance
mcp = FastMCP("context-memory-mcp")

# Module-level references for auto features (set during _wire_interception)
_auto_save_middleware = None
_context_injector = None
_file_watcher = None


def get_auto_save():
    """Get the auto-save middleware instance (set during wiring)."""
    return _auto_save_middleware


def get_injector():
    """Get the context injector instance (set during wiring)."""
    return _context_injector


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
    # Phase 4
    from context_memory_mcp.context import register as register_context

    register_context(mcp)


def _wire_interception(mcp: FastMCP) -> None:
    """Monkey-patch mcp.call_tool for auto-save and auto-retrieve.

    Intercepts every tool call/response to:
    1. Auto-retrieve context before tool execution
    2. Auto-save tool call + response to ChromaDB
    3. Append context to string results
    """
    from context_memory_mcp.auto_retrieve import ContextInjector
    from context_memory_mcp.auto_save import AutoSaveMiddleware
    from context_memory_mcp.chat_store import get_store
    from context_memory_mcp.config import get_config

    global _auto_save_middleware, _context_injector

    config = get_config()
    store = get_store()

    # Create instances
    _auto_save_middleware = AutoSaveMiddleware(store, config)
    _context_injector = ContextInjector(store, config)

    # Tools that don't benefit from context injection
    SKIP_CONTEXT_TOOLS = frozenset({
        "ping", "list_sessions", "get_file_graph", "delete_session",
    })

    # Save original
    _original_call_tool = mcp.call_tool

    async def _intercepted_call_tool(name: str, arguments: dict[str, Any]):
        # Pre-tool: retrieve context (if enabled and tool benefits)
        context_block = None
        if config.auto_retrieve and name not in SKIP_CONTEXT_TOOLS:
            session_id = _auto_save_middleware.session_id if _auto_save_middleware else None
            context_block = _context_injector.inject(query=name, session_id=session_id)

        # Pre-tool: capture tool call for auto-save
        if config.auto_save and _auto_save_middleware:
            _auto_save_middleware.on_tool_call(name, arguments)

        # Execute original tool
        result = await _original_call_tool(name, arguments)

        # Post-tool: capture tool response for auto-save
        if config.auto_save and _auto_save_middleware:
            _auto_save_middleware.on_tool_response(name, arguments, result)

        # Post-tool: append context to result (only if string)
        if context_block and isinstance(result, str):
            result = result + "\n\n" + context_block

        return result

    mcp.call_tool = _intercepted_call_tool


def run_server() -> None:
    """Run the MCP server on stdio transport.

    This function blocks until the server is stopped.
    FastMCP manages its own event loop — do NOT wrap in asyncio.run().

    Automatic features (auto-save, auto-retrieve, auto-track) are
    wired up via monkey-patching mcp.call_tool. Config loaded from
    ./data/config.json via get_config().
    """
    register_all()

    # Load config
    from context_memory_mcp.config import get_config

    config = get_config()

    # Start file watcher in background (runs its own OS thread)
    global _file_watcher
    if config.auto_track:
        from context_memory_mcp.file_graph import get_graph
        from context_memory_mcp.file_watcher import FileWatcher

        graph = get_graph()
        _file_watcher = FileWatcher(config.watch_dirs, config.watch_ignore_dirs, graph)
        _file_watcher.start()
        logging.info("File watcher started on %s", config.watch_dirs)

    # Wire interception for auto-save + auto-retrieve
    if config.auto_save or config.auto_retrieve:
        _wire_interception(mcp)
        logging.info("Auto-save/auto-retrieve interception wired")

    try:
        mcp.run(transport="stdio")  # Blocks until stdin closes
    finally:
        # Clean shutdown
        if _file_watcher:
            _file_watcher.stop()
        from context_memory_mcp.chat_store import get_store

        store = get_store()
        store.close()
        logging.info("Server shut down cleanly")
