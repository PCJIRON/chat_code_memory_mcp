"""Token-efficient context retrieval.

Combines chat history, file graph, and embeddings to build
concise, relevant context windows for LLM interactions.
"""

from __future__ import annotations

from typing import Any


class ContextWindow:
    """Represents a token-limited context window.

    Attributes:
        content: The assembled context text.
        token_count: Estimated number of tokens in the content.
        max_tokens: Maximum allowed token count.
        sources: List of source identifiers included in the context.
    """

    def __init__(
        self,
        content: str = "",
        token_count: int = 0,
        max_tokens: int = 4000,
        sources: list[str] | None = None,
    ) -> None:
        """Initialize a ContextWindow.

        Args:
            content: Initial context text.
            token_count: Initial token count estimate.
            max_tokens: Maximum token budget.
            sources: List of sources contributing to the context.
        """
        ...

    def fits(self, additional_text: str) -> bool:
        """Check if additional text would fit within the token budget.

        Args:
            additional_text: Text to potentially add.

        Returns:
            True if the text fits, False otherwise.
        """
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serialize the context window to a dictionary.

        Returns:
            Dictionary representation for MCP tool responses.
        """
        ...


class ContextBuilder:
    """Builds token-efficient context windows from multiple sources.

    Combines recent chat history, relevant file content, and
    semantic search results into a single context window
    optimized for LLM consumption.

    Attributes:
        max_tokens: Maximum token budget for the context window.
    """

    def __init__(self, max_tokens: int = 4000) -> None:
        """Initialize the ContextBuilder.

        Args:
            max_tokens: Maximum token budget for the context window.
        """
        ...

    def build(
        self,
        query: str,
        session_id: str | None = None,
        active_files: list[str] | None = None,
    ) -> ContextWindow:
        """Build a context window relevant to the given query.

        Args:
            query: The user's query or current request.
            session_id: Optional session to pull recent history from.
            active_files: Optional list of currently open/active files.

        Returns:
            A ContextWindow with relevant context assembled.
        """
        ...

    def _estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in a text string.

        Uses a simple character-based heuristic (roughly 4 chars/token).

        Args:
            text: Text to estimate tokens for.

        Returns:
            Estimated token count.
        """
        ...
