"""Token-efficient context retrieval.

Combines chat history, file graph, and embeddings to build
concise, relevant context windows for LLM interactions.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import Field


def _estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text string.

    Uses a simple character-based heuristic (roughly 4 chars/token).

    Args:
        text: Text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    return len(text) // 4


def get_minimal_context(messages: list[dict], max_tokens: int = 100) -> "ContextWindow":
    """Compress messages to fit ~100 token budget.

    Strategy: Extract key info only — most recent user query, 1-2 recent
    assistant replies. Truncate content at token boundary, append '...'
    if truncated.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        max_tokens: Target token budget.

    Returns:
        ContextWindow with compressed content.
    """
    if not messages:
        return ContextWindow(content="", token_count=0, max_tokens=max_tokens)

    parts = []

    # Most recent user message
    user_msgs = [m for m in messages if m.get("role") == "user"]
    if user_msgs:
        last_user = user_msgs[-1]
        content = last_user.get("content", "")
        if _estimate_tokens(content) > 50:
            content = content[:200] + "..."
        parts.append(f"User: {content}")

    # Most recent assistant reply
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    if assistant_msgs:
        last_asst = assistant_msgs[-1]
        content = last_asst.get("content", "")
        if _estimate_tokens(content) > 50:
            content = content[:200] + "..."
        parts.append(f"Assistant: {content}")

    result = "\n".join(parts)
    return ContextWindow(content=result, token_count=_estimate_tokens(result), max_tokens=max_tokens)


def format_with_detail(results: dict | list, level: str = "summary") -> str:
    """Format results by detail level.

    Args:
        results: Query results (dict or list of messages).
        level: "minimal" (~100 tokens), "summary" (~300 tokens), "full" (raw).

    Returns:
        Formatted string.

    Raises:
        ValueError: If level is not one of minimal, summary, or full.
    """
    if level not in ("minimal", "summary", "full"):
        raise ValueError(f"Invalid detail level: {level}. Must be minimal, summary, or full.")

    if not results:
        return json.dumps({"results": [], "detail_level": level}, indent=2)

    if level == "minimal":
        # ~100 tokens: key info only — last query, last reply, counts
        if isinstance(results, list):
            user_msgs = [m for m in results if m.get("role") == "user"]
            assistant_msgs = [m for m in results if m.get("role") == "assistant"]
            parts = [f"Total messages: {len(results)}"]
            if user_msgs:
                content = user_msgs[-1].get("content", "")
                if _estimate_tokens(content) > 40:
                    content = content[:160] + "..."
                parts.append(f"Last user: {content}")
            if assistant_msgs:
                content = assistant_msgs[-1].get("content", "")
                if _estimate_tokens(content) > 40:
                    content = content[:160] + "..."
                parts.append(f"Last assistant: {content}")
            return "\n".join(parts)
        else:
            # dict results — extract summary info
            total = results.get("total_found", 0)
            query = results.get("query", "")
            parts = [f"Query: {query}", f"Results: {total}"]
            if results.get("results"):
                last_result = results["results"][-1]
                content = last_result.get("content", "")
                if _estimate_tokens(content) > 50:
                    content = content[:200] + "..."
                parts.append(f"Last: {content}")
            return "\n".join(parts)

    elif level == "summary":
        # ~300 tokens: adds headers, file list, match highlights
        if isinstance(results, list):
            parts = [f"Total messages: {len(results)}", "---"]
            for msg in results[:5]:  # limit to 5 messages
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                ts = msg.get("timestamp", "")
                header = f"[{role}]"
                if ts:
                    header += f" {ts}"
                if _estimate_tokens(content) > 50:
                    content = content[:200] + "..."
                parts.append(f"{header}\n{content}")
            if len(results) > 5:
                parts.append(f"... and {len(results) - 5} more messages")
            return "\n".join(parts)
        else:
            # dict results
            total = results.get("total_found", 0)
            query = results.get("query", "")
            parts = [f"Query: {query}", f"Total results: {total}", "---"]
            for item in results.get("results", [])[:5]:
                role = item.get("role", "unknown")
                content = item.get("content", "")
                dist = item.get("distance", "N/A")
                sim = item.get("similarity", "N/A")
                if _estimate_tokens(content) > 50:
                    content = content[:200] + "..."
                parts.append(f"[{role}] (similarity: {sim})\n{content}")
            if len(results.get("results", [])) > 5:
                parts.append(f"... and {len(results['results']) - 5} more results")
            return "\n".join(parts)

    else:  # full
        return json.dumps(results, indent=2)


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
        self.content = content
        self.token_count = token_count
        self.max_tokens = max_tokens
        self.sources = sources or []

    def fits(self, additional_text: str) -> bool:
        """Check if additional text would fit within the token budget.

        Args:
            additional_text: Text to potentially add.

        Returns:
            True if the text fits, False otherwise.
        """
        additional_tokens = _estimate_tokens(additional_text)
        return (self.token_count + additional_tokens) <= self.max_tokens

    def to_dict(self) -> dict[str, Any]:
        """Serialize the context window to a dictionary.

        Returns:
            Dictionary representation for MCP tool responses.
        """
        return {
            "content": self.content,
            "token_count": self.token_count,
            "max_tokens": self.max_tokens,
            "sources": self.sources,
        }


class HybridContextBuilder:
    """Builds token-efficient context windows from multiple sources.

    Uses IntentClassifier to route queries to the appropriate data sources:
    - Chat intent: queries ChromaDB chat history
    - File intent: queries ChromaDB file changes
    - Both intent: queries both sources, merges results
    Token budget enforced with 60% chat / 40% file split.

    Attributes:
        store: ChatStore instance for querying messages.
        file_graph: Optional FileGraph for structural queries (T11).
        classifier: IntentClassifier for intent routing.
        max_tokens: Maximum token budget for the context window.
        chat_budget_pct: Percentage of budget for chat context.
    """

    def __init__(
        self,
        store,
        file_graph=None,
        classifier=None,
        max_tokens: int = 4000,
        chat_budget_pct: float = 0.6,
    ) -> None:
        """Initialize HybridContextBuilder.

        Args:
            store: ChatStore instance.
            file_graph: Optional FileGraph instance.
            classifier: IntentClassifier instance.
            max_tokens: Maximum token budget.
            chat_budget_pct: Fraction of budget for chat (rest for files).
        """
        self.store = store
        self.file_graph = file_graph
        self.classifier = classifier
        self.max_tokens = max_tokens
        self.chat_budget_pct = chat_budget_pct

    def build(
        self,
        query: str,
        session_id: str | None = None,
        active_files: list[str] | None = None,
    ) -> "ContextWindow":
        """Build a context window relevant to the given query.

        Classifies intent, routes to appropriate data sources,
        merges results, and enforces token budget.

        Args:
            query: The user's query or current request.
            session_id: Optional session to pull recent history from.
            active_files: Optional list of currently open/active files.

        Returns:
            A ContextWindow with merged context from relevant sources.
        """
        # Classify intent
        if self.classifier:
            intent = self.classifier.classify(query)
        else:
            intent = "both"  # Fallback without classifier

        parts: list[str] = []
        sources: list[str] = []
        chat_budget = int(self.max_tokens * self.chat_budget_pct)
        file_budget = self.max_tokens - chat_budget

        # Retrieve chat context
        if intent in ("chat", "both"):
            chat_results = self.store.query_messages(
                query=query, top_k=5, session_id=session_id
            )
            if chat_results:
                chat_content = format_with_detail(
                    {"query": query, "results": chat_results}, "summary"
                )
                if _estimate_tokens(chat_content) <= chat_budget + 50:
                    parts.append(chat_content)
                    sources.append("chat_history")
                else:
                    # Truncate to fit budget
                    truncated = chat_content[: chat_budget * 4]
                    parts.append(truncated)
                    sources.append("chat_history")

        # Retrieve file change context
        if intent in ("file", "both"):
            file_results = self.store.query_file_changes(
                query=query, top_k=5
            )
            if file_results:
                file_content = self._format_file_changes(file_results)
                if _estimate_tokens(file_content) <= file_budget + 50:
                    parts.append(file_content)
                    sources.append("file_changes")
                else:
                    truncated = file_content[: file_budget * 4]
                    parts.append(truncated)
                    sources.append("file_changes")

        # Merge content
        content = "\n---\n".join(parts) if parts else (
            f"No relevant context found for: {query}"
        )

        return ContextWindow(
            content=content,
            token_count=_estimate_tokens(content),
            max_tokens=self.max_tokens,
            sources=sources,
        )

    @staticmethod
    def _format_file_changes(results: list[dict]) -> str:
        """Format file change results into a readable string.

        Args:
            results: List of file change result dicts from query_file_changes.

        Returns:
            Formatted string with file change information.
        """
        parts = [f"File Changes ({len(results)} results)", "---"]
        for r in results:
            change_type = r.get("change_type", "unknown")
            file_path = r.get("file_path", "unknown")
            content = r.get("content", "")
            ts = r.get("timestamp", "")
            sim = r.get("similarity", "N/A")

            entry = f"[{change_type}] {file_path}"
            if ts:
                entry += f" ({ts})"
            entry += f" [similarity: {sim}]"
            if content:
                if _estimate_tokens(content) > 50:
                    content = content[:200] + "..."
                entry += f"\n{content}"
            parts.append(entry)

        return "\n".join(parts)


# Backward compatibility alias — ContextBuilder now points to HybridContextBuilder
ContextBuilder = HybridContextBuilder


def register(mcp: Any) -> None:
    """Register get_context MCP tool.

    Creates HybridContextBuilder with store and optional graph/classifier.

    Args:
        mcp: FastMCP server instance.
    """
    from context_memory_mcp.chat_store import get_store

    store = get_store()

    # Try to get optional dependencies (may not be wired yet)
    file_graph = None
    classifier = None
    try:
        from context_memory_mcp.file_graph import get_graph
        file_graph = get_graph()
    except Exception:
        pass
    try:
        from context_memory_mcp.intent_classifier import get_intent_classifier
        classifier = get_intent_classifier(embedding_function=store._ef)
    except Exception:
        pass

    builder = HybridContextBuilder(
        store=store, file_graph=file_graph, classifier=classifier
    )

    @mcp.tool(
        name="get_context",
        description="Get token-efficient context for a query",
    )
    async def get_context(
        query: Annotated[str, Field(description="Search query")],
        session_id: Annotated[str | None, Field(description="Optional session filter")] = None,
        detail_level: Annotated[str, Field(description="minimal, summary, or full")] = "summary",
        active_files: Annotated[list[str] | None, Field(description="Optional active file paths")] = None,
    ) -> str:
        """Get token-efficient context for a query.

        Args:
            query: Search query.
            session_id: Optional session filter.
            detail_level: Output detail level (minimal, summary, full).
            active_files: Optional active file paths.

        Returns:
            JSON string with context content and token count.
        """
        window = builder.build(query=query, session_id=session_id, active_files=active_files)
        return json.dumps({
            "query": query,
            "content": window.content,
            "token_count": window.token_count,
            "detail_level": detail_level,
        }, indent=2)
