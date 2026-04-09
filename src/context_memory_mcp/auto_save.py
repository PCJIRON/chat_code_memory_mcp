"""Auto-save middleware for MCP server.

Intercepts tool calls and responses, buffers them, and flushes to ChromaDB.
All methods are synchronous — ChromaDB store_messages() is sync.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from context_memory_mcp.chat_store import ChatStore
from context_memory_mcp.config import AutoConfig, get_config


class AutoSaveMiddleware:
    """Intercepts MCP tool calls/responses and auto-saves to ChromaDB.

    Buffers tool call + response pairs, flushing on response.
    Session ID is auto-generated UUID if not provided.

    Attributes:
        store: ChatStore instance for persistence.
        config: AutoConfig for feature toggles.
        session_id: Unique session identifier for auto-saved messages.
    """

    def __init__(
        self,
        store: ChatStore,
        config: AutoConfig | None = None,
        session_id: str | None = None,
    ) -> None:
        """Initialize AutoSaveMiddleware.

        Args:
            store: ChatStore instance for saving messages.
            config: Configuration for feature toggles. Defaults to get_config().
            session_id: Session identifier. Auto-generated UUID if omitted.
        """
        self.store = store
        self.config = config or get_config()
        self.session_id = session_id or str(uuid.uuid4())
        self._buffer: list[dict[str, str]] = []
        self._enabled = self.config.auto_save

    def on_tool_call(self, name: str, arguments: dict) -> None:
        """Capture a tool call event and buffer it.

        Args:
            name: Tool name that was called.
            arguments: Tool call arguments dict.
        """
        if not self._enabled:
            return
        self._buffer.append({
            "role": "tool_call",
            "content": json.dumps({"tool": name, "arguments": arguments}),
            "session_id": self.session_id,
        })

    def on_tool_response(self, name: str, arguments: dict, result: Any) -> None:
        """Capture a tool response event, buffer it, and flush.

        Args:
            name: Tool name that produced the response.
            arguments: Original tool call arguments.
            result: Tool response (any type, truncated if large).
        """
        if not self._enabled:
            return
        self._buffer.append({
            "role": "tool_response",
            "content": json.dumps({"tool": name, "result": _truncate_result(result)}),
            "session_id": self.session_id,
        })
        self._flush()

    def _flush(self) -> None:
        """Flush buffered messages to ChromaDB.

        Clears buffer on success. Preserves buffer on failure for retry.
        """
        if not self._buffer:
            return
        try:
            self.store.store_messages(self._buffer, session_id=self.session_id)
            self._buffer.clear()
        except Exception as e:
            logging.error(f"Auto-save flush failed: {e}")
            # Don't clear buffer on failure — retry-safe


def _truncate_result(result: Any, max_len: int = 500) -> str:
    """Truncate a result value to max_len characters.

    Converts non-string results via json.dumps. Appends '...' if truncated.

    Args:
        result: Value to truncate (any type).
        max_len: Maximum string length before truncation.

    Returns:
        Truncated string representation.
    """
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    return text[:max_len] + "..." if len(text) > max_len else text
