"""Auto-retrieve context injector.

Queries ChromaDB before tool calls and returns formatted context
to append to the tool response. Uses ~300 token budget by default.
"""

from __future__ import annotations

import logging

from context_memory_mcp.chat_store import ChatStore
from context_memory_mcp.config import AutoConfig, get_config
from context_memory_mcp.context import _estimate_tokens, format_with_detail


class ContextInjector:
    """Auto-queries ChromaDB and injects context into tool responses.

    Uses format_with_detail(level='summary') for ~300 token output.
    Enforces token budget via _estimate_tokens().

    Attributes:
        store: ChatStore instance for querying messages.
        config: AutoConfig for feature toggles and token budget.
    """

    def __init__(
        self,
        store: ChatStore,
        config: AutoConfig | None = None,
    ) -> None:
        """Initialize ContextInjector.

        Args:
            store: ChatStore instance for querying messages.
            config: Configuration for feature toggles. Defaults to get_config().
        """
        self.store = store
        self.config = config or get_config()
        self.max_tokens = self.config.auto_context_tokens
        self._enabled = self.config.auto_retrieve

    def inject(self, query: str, session_id: str | None = None) -> str:
        """Query ChromaDB and return formatted context string.

        Args:
            query: Query text to search for in chat history.
            session_id: Optional session to filter results.

        Returns:
            Formatted context string with [Auto-Context] header, or empty string.
        """
        if not self._enabled:
            return ""
        try:
            results = self.store.query_messages(query=query, top_k=5, session_id=session_id)
            if not results:
                return ""
            context = format_with_detail({"query": query, "results": results}, level="summary")
            # Verify token budget
            if _estimate_tokens(context) > self.max_tokens + 50:
                # Trim if over budget
                context = context[: self.max_tokens * 4]
            return f"[Auto-Context]\n{context}" if context else ""
        except Exception as e:
            logging.error(f"Context injection failed: {e}")
            return ""
