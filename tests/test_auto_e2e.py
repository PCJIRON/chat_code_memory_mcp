"""End-to-end integration tests for automatic save/track/retrieve pipeline.

Tests the complete pipeline: tool call → auto-save → auto-retrieve → file change → auto-track.
Uses synchronous testing (no real threading, no monkey-patching in tests).
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from context_memory_mcp.auto_retrieve import ContextInjector
from context_memory_mcp.auto_save import AutoSaveMiddleware
from context_memory_mcp.chat_store import ChatStore
from context_memory_mcp.config import AutoConfig
from context_memory_mcp.context import _estimate_tokens
from context_memory_mcp.file_watcher import FileWatcher


@pytest.fixture
def chat_store(tmp_path):
    """Create an isolated ChatStore for testing."""
    store = ChatStore(chroma_path=str(tmp_path / "chromadb"))
    yield store
    store.close()


@pytest.fixture
def config_all_enabled():
    """AutoConfig with all features enabled."""
    return AutoConfig(auto_save=True, auto_retrieve=True, auto_track=True)


class TestAutoSaveE2E:
    """End-to-end tests for auto-save pipeline."""

    def test_auto_save_on_tool_call(self, chat_store, config_all_enabled):
        """Tool call should buffer, response should flush to ChromaDB."""
        mw = AutoSaveMiddleware(chat_store, config_all_enabled, session_id="e2e-session")

        # Simulate tool call
        mw.on_tool_call("query_chat", {"query": "how does chromadb work"})
        assert len(mw._buffer) == 1
        assert mw._buffer[0]["role"] == "tool_call"

        # Simulate tool response
        mw.on_tool_response("query_chat", {"query": "how does chromadb work"}, "ChromaDB stores embeddings.")
        assert len(mw._buffer) == 0  # Flushed

        # Verify stored in ChromaDB
        results = chat_store.query_messages(
            query="chromadb", session_id="e2e-session", top_k=5
        )
        assert len(results) == 2
        roles = [r["role"] for r in results]
        assert "tool_call" in roles
        assert "tool_response" in roles


class TestAutoRetrieveE2E:
    """End-to-end tests for auto-retrieve pipeline."""

    def test_auto_retrieve_injects_context(self, chat_store, config_all_enabled):
        """Context should be appended to tool result string."""
        # Populate ChromaDB
        chat_store.store_messages([
            {"role": "user", "content": "How do I use vector databases for search?"},
            {"role": "assistant", "content": "Vector databases store embeddings for semantic search."},
        ], session_id="retrieve-session")

        injector = ContextInjector(chat_store, config_all_enabled)
        result = injector.inject(query="vector search", session_id="retrieve-session")

        assert "[SYSTEM CONTEXT:" in result
        assert "vector" in result.lower() or "search" in result.lower()

    def test_auto_retrieve_respects_token_budget_e2e(self, chat_store):
        """Stored many messages, context should be within token budget."""
        config = AutoConfig(auto_retrieve=True, auto_context_tokens=100)
        # Store many messages
        messages = [
            {"role": "user", "content": f"Message {i}: " + "x" * 80}
            for i in range(20)
        ]
        chat_store.store_messages(messages, session_id="budget-e2e")

        injector = ContextInjector(chat_store, config)
        result = injector.inject(query="Message", session_id="budget-e2e")

        if result:
            # Extract content after [SYSTEM CONTEXT: ...] header
            lines = result.split("\n", 1)
            content = lines[1] if len(lines) > 1 else result
            tokens = _estimate_tokens(content)
            # Allow 50 token overflow margin
            assert tokens <= config.auto_context_tokens + 50


class TestFileWatcherE2E:
    """End-to-end tests for file watcher with real file changes."""

    def test_auto_track_file_change(self, tmp_path, config_all_enabled):
        """Modify file in watched directory, verify graph updated."""
        mock_graph = MagicMock()
        watch_dir = str(tmp_path / "src")
        os.makedirs(watch_dir)

        # Create a test file
        test_file = os.path.join(watch_dir, "module.py")
        with open(test_file, "w") as f:
            f.write("def hello(): pass")

        watcher = FileWatcher([watch_dir], [".git"], mock_graph)
        watcher.start()

        # Wait for observer to start
        import time
        time.sleep(0.2)

        # Modify the file
        with open(test_file, "w") as f:
            f.write("def hello(): return 'world'")

        # Wait for debounce + processing
        time.sleep(0.8)

        watcher.stop()

        # Graph should have been updated at least once
        assert mock_graph.update_graph.call_count >= 1


class TestDisabledFeaturesE2E:
    """Test that disabled features don't interfere with normal operation."""

    def test_disabled_features_do_not_interfere(self, chat_store):
        """All features disabled → middleware and injector should be no-ops."""
        config = AutoConfig(auto_save=False, auto_retrieve=False, auto_track=False)

        # Auto-save disabled
        mw = AutoSaveMiddleware(chat_store, config, session_id="disabled-e2e")
        mw.on_tool_call("test", {})
        mw.on_tool_response("test", {}, "result")
        assert len(mw._buffer) == 0

        # Auto-retrieve disabled
        chat_store.store_messages([
            {"role": "user", "content": "test message"},
        ], session_id="disabled-e2e")
        injector = ContextInjector(chat_store, config)
        result = injector.inject(query="test", session_id="disabled-e2e")
        assert result == ""


class TestFullPipelineE2E:
    """Full pipeline test: chat → auto-save → auto-retrieve → verify."""

    def test_full_pipeline(self, chat_store, config_all_enabled):
        """Complete pipeline: store messages, auto-save, auto-retrieve context."""
        # Step 1: Auto-save captures tool interaction
        mw = AutoSaveMiddleware(chat_store, config_all_enabled, session_id="full-pipeline")
        mw.on_tool_call("store_chat", {"messages": [{"role": "user", "content": "What is ChromaDB?"}]})
        mw.on_tool_response("store_chat", {"messages": []}, '{"stored": 1}')

        # Step 2: Verify messages stored
        results = chat_store.query_messages(
            query="ChromaDB", session_id="full-pipeline", top_k=5
        )
        assert len(results) >= 1

        # Step 3: Auto-retrieve finds saved context
        injector = ContextInjector(chat_store, config_all_enabled)
        context = injector.inject(query="ChromaDB", session_id="full-pipeline")
        assert "[SYSTEM CONTEXT:" in context


class TestMonkeyPatchQueryExtraction:
    """Test that the monkey-patch interception extracts real queries, not tool names."""

    @pytest.fixture()
    def isolated_store(self, tmp_path):
        """Create an isolated ChatStore for testing."""
        store = ChatStore(chroma_path=str(tmp_path / "chromadb"))
        yield store
        store.close()

    def test_intercepted_call_uses_query_arg_not_tool_name(self, isolated_store, tmp_path):
        """Monkey-patched call_tool should extract 'query' from arguments, not use tool name."""
        from context_memory_mcp.mcp_server import _extract_query_from_arguments

        # Verify the helper extracts query correctly
        assert _extract_query_from_arguments({"query": "how does vector search work"}) == "how does vector search work"
        assert _extract_query_from_arguments({"query": "what are dependencies"}) == "what are dependencies"
        # Should not return the tool name
        assert _extract_query_from_arguments({"query": "real query", "top_k": 5}) == "real query"

    def test_intercepted_call_extract_fallback_keys(self):
        """Fallback should use conversation, search, text, content in priority order."""
        from context_memory_mcp.mcp_server import _extract_query_from_arguments

        assert _extract_query_from_arguments({"conversation": "conv text"}) == "conv text"
        assert _extract_query_from_arguments({"search": "search terms"}) == "search terms"
        assert _extract_query_from_arguments({"text": "some text"}) == "some text"
        assert _extract_query_from_arguments({"content": "content here"}) == "content here"

    def test_intercepted_call_join_fallback(self):
        """When no known key exists, join all values."""
        from context_memory_mcp.mcp_server import _extract_query_from_arguments

        result = _extract_query_from_arguments({"foo": "bar", "baz": "qux"})
        assert "bar" in result
        assert "qux" in result

    def test_intercepted_call_empty_arguments(self):
        """Empty arguments should return empty string."""
        from context_memory_mcp.mcp_server import _extract_query_from_arguments

        assert _extract_query_from_arguments({}) == ""

    def test_intercepted_call_empty_query_falls_back(self):
        """Empty query string should fall back to next available key."""
        from context_memory_mcp.mcp_server import _extract_query_from_arguments

        # Empty query should fall through to text
        result = _extract_query_from_arguments({"query": "", "text": "fallback text"})
        assert result == "fallback text"
