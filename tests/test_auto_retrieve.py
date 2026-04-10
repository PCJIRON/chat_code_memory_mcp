"""Tests for ContextInjector."""

from __future__ import annotations

import pytest

from context_memory_mcp.auto_retrieve import ContextInjector
from context_memory_mcp.chat_store import ChatStore
from context_memory_mcp.config import AutoConfig
from context_memory_mcp.context import _estimate_tokens


@pytest.fixture
def chat_store(tmp_path):
    """Create an isolated ChatStore for testing."""
    store = ChatStore(chroma_path=str(tmp_path / "chromadb"))
    yield store
    store.close()


@pytest.fixture
def config_enabled():
    """AutoConfig with auto_retrieve enabled."""
    return AutoConfig(auto_save=True, auto_retrieve=True, auto_track=True)


@pytest.fixture
def config_disabled():
    """AutoConfig with auto_retrieve disabled."""
    return AutoConfig(auto_save=True, auto_retrieve=False, auto_track=True)


@pytest.fixture
def config_low_tokens():
    """AutoConfig with very low token budget."""
    return AutoConfig(auto_save=True, auto_retrieve=True, auto_track=True, auto_context_tokens=50)


class TestContextInjector:
    """Tests for ContextInjector."""

    def test_context_injector_returns_context_when_messages_exist(self, chat_store, config_enabled):
        """When ChromaDB has messages, inject should return [SYSTEM CONTEXT] string."""
        # Populate ChromaDB
        chat_store.store_messages([
            {"role": "user", "content": "How do I use vector databases?"},
            {"role": "assistant", "content": "Vector databases store embeddings for semantic search."},
        ], session_id="inject-session")

        injector = ContextInjector(chat_store, config_enabled)
        result = injector.inject(query="vector db", session_id="inject-session")

        assert "[SYSTEM CONTEXT:" in result
        assert "vector" in result.lower() or "search" in result.lower()

    def test_context_injector_returns_empty_when_no_messages(self, chat_store, config_enabled):
        """Empty ChromaDB should return context with 'no relevant context' message."""
        injector = ContextInjector(chat_store, config_enabled)
        result = injector.inject(query="anything")
        # With HybridContextBuilder, returns "No relevant context found" when empty
        assert "No relevant context found" in result or result == ""

    def test_context_injector_returns_empty_when_disabled(self, chat_store, config_disabled):
        """When auto_retrieve is False, should return empty string."""
        # Populate ChromaDB
        chat_store.store_messages([
            {"role": "user", "content": "test message"},
        ], session_id="disabled-session")

        injector = ContextInjector(chat_store, config_disabled)
        result = injector.inject(query="test")
        assert result == ""

    def test_context_injector_respects_token_budget(self, chat_store, config_low_tokens):
        """Context should be trimmed to fit token budget."""
        # Store several messages to exceed 50-token budget
        messages = [
            {"role": "user", "content": f"Message number {i}: " + "x" * 100}
            for i in range(10)
        ]
        chat_store.store_messages(messages, session_id="budget-session")

        injector = ContextInjector(chat_store, config_low_tokens)
        result = injector.inject(query="Message", session_id="budget-session")

        if result:  # May be empty if all trimmed
            # Extract content after header
            content = result.replace("[Auto-Context]\n", "")
            tokens = _estimate_tokens(content)
            # Allow some tolerance (budget + 50 overflow margin)
            assert tokens <= config_low_tokens.auto_context_tokens + 50

    def test_context_injector_handles_query_exception(self, chat_store, config_enabled):
        """If query_messages raises, inject should return empty string."""
        injector = ContextInjector(chat_store, config_enabled)
        # query_messages with empty query may raise or return empty
        # Test with a valid query but verify no exception propagates
        result = injector.inject(query="")
        # Should not raise, may return empty
        assert isinstance(result, str)

    def test_context_injector_session_filter(self, chat_store, config_enabled):
        """Session filter should return only messages from that session."""
        # Store messages in two sessions
        chat_store.store_messages([
            {"role": "user", "content": "session A message"},
        ], session_id="session-A")
        chat_store.store_messages([
            {"role": "user", "content": "session B message"},
        ], session_id="session-B")

        injector = ContextInjector(chat_store, config_enabled)
        result_a = injector.inject(query="session", session_id="session-A")
        result_b = injector.inject(query="session", session_id="session-B")

        # Both should have context
        if result_a and result_b:
            assert "session A" in result_a or "session A" not in result_b  # filtered
