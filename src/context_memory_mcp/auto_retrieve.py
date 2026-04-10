"""Auto-retrieve context injector.

Queries the hybrid context builder before tool calls and returns
formatted context to inject into tool responses. Uses dual injection:
(1) System-prompt-like prefix for response prepend, (2) response append
fallback. ~300 token budget by default.
"""

from __future__ import annotations

import logging

from context_memory_mcp.chat_store import ChatStore
from context_memory_mcp.config import AutoConfig, get_config
from context_memory_mcp.context import (
    HybridContextBuilder,
    _estimate_tokens,
    format_with_detail,
)


class ContextInjector:
    """Auto-queries the hybrid context builder and injects context.

    Uses dual injection strategy:
    1. System-prompt-like prefix: [SYSTEM CONTEXT: ...] for prepend
    2. Response append fallback: [Auto-Context] ... for append

    Attributes:
        builder: HybridContextBuilder for multi-source retrieval.
        config: AutoConfig for feature toggles and token budget.
    """

    def __init__(
        self,
        store: ChatStore,
        config: AutoConfig | None = None,
        builder: HybridContextBuilder | None = None,
    ) -> None:
        """Initialize ContextInjector.

        Args:
            store: ChatStore instance for querying messages.
            config: Configuration for feature toggles. Defaults to get_config().
            builder: HybridContextBuilder instance. Auto-created if None.
        """
        self.store = store
        self.config = config or get_config()
        self.max_tokens = self.config.auto_context_tokens
        self._enabled = self.config.auto_retrieve

        if builder is not None:
            self.builder = builder
        else:
            # Fallback: create a basic builder without classifier/graph
            self.builder = HybridContextBuilder(
                store=store, max_tokens=self.max_tokens
            )

    def inject(self, query: str, session_id: str | None = None) -> str:
        """Build context and return dual-format string.

        Dual injection:
        1. System-prompt prefix: [SYSTEM CONTEXT: ...]\n{content}
        2. Sources footer: [Sources: ...]

        Args:
            query: Query text to search for in context.
            session_id: Optional session to filter results.

        Returns:
            Formatted context string with [SYSTEM CONTEXT] header, or empty string.
        """
        if not self._enabled:
            return ""
        try:
            context_window = self.builder.build(
                query=query, session_id=session_id
            )
            if context_window.token_count == 0:
                return ""

            # Verify token budget
            if _estimate_tokens(context_window.content) > self.max_tokens + 50:
                # Trim if over budget
                content = context_window.content[: self.max_tokens * 4]
            else:
                content = context_window.content

            # Dual injection format: system prompt prefix + sources footer
            sources_str = ", ".join(context_window.sources) if context_window.sources else "none"
            return (
                f"[SYSTEM CONTEXT: sources={sources_str}]\n"
                f"{content}\n"
                f"[Sources: {sources_str}]"
            )
        except Exception as e:
            logging.error(f"Context injection failed: {e}")
            return ""
