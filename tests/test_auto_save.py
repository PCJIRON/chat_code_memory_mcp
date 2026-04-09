"""Tests for AutoSaveMiddleware."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from context_memory_mcp.auto_save import AutoSaveMiddleware, _truncate_result
from context_memory_mcp.chat_store import ChatStore
from context_memory_mcp.config import AutoConfig


@pytest.fixture
def chat_store(tmp_path):
    """Create an isolated ChatStore for testing."""
    store = ChatStore(chroma_path=str(tmp_path / "chromadb"))
    yield store
    store.close()


@pytest.fixture
def config_enabled():
    """AutoConfig with all features enabled."""
    return AutoConfig(auto_save=True, auto_retrieve=True, auto_track=True)


@pytest.fixture
def config_disabled():
    """AutoConfig with auto_save disabled."""
    return AutoConfig(auto_save=False, auto_retrieve=False, auto_track=False)


class TestAutoSaveMiddleware:
    """Tests for AutoSaveMiddleware."""

    def test_auto_save_initializes_with_session_id(self, chat_store, config_enabled):
        """Session ID should be a valid UUID string."""
        mw = AutoSaveMiddleware(chat_store, config_enabled)
        # Should not raise
        uuid.UUID(mw.session_id)
        assert mw._enabled is True

    def test_auto_save_captures_tool_call_and_response(self, chat_store, config_enabled):
        """Tool call + response should buffer and flush to ChromaDB."""
        mw = AutoSaveMiddleware(chat_store, config_enabled, session_id="test-session")
        mw.on_tool_call("query_chat", {"query": "test"})
        assert len(mw._buffer) == 1
        mw.on_tool_response("query_chat", {"query": "test"}, "response text")
        # After response, buffer should be flushed
        assert len(mw._buffer) == 0
        # Verify messages were stored
        results = chat_store.query_messages(
            query="test", session_id="test-session", top_k=5
        )
        assert len(results) == 2
        roles = [r["role"] for r in results]
        assert "tool_call" in roles
        assert "tool_response" in roles

    def test_auto_save_truncates_large_results(self, chat_store, config_enabled):
        """Results > 500 chars should be truncated with '...'."""
        mw = AutoSaveMiddleware(chat_store, config_enabled, session_id="test-session")
        large_result = "x" * 2000
        mw.on_tool_call("test_tool", {})
        mw.on_tool_response("test_tool", {}, large_result)
        # Stored content should be truncated
        results = chat_store.query_messages(query="x", session_id="test-session", top_k=5)
        response_msg = [r for r in results if r["role"] == "tool_response"]
        assert len(response_msg) == 1
        content = json.loads(response_msg[0]["content"])
        assert len(content["result"]) < 1000
        assert content["result"].endswith("...")

    def test_auto_save_disabled_does_nothing(self, chat_store, config_disabled):
        """When disabled, tool call/response should not buffer anything."""
        mw = AutoSaveMiddleware(chat_store, config_disabled, session_id="test-session")
        mw.on_tool_call("test_tool", {})
        assert len(mw._buffer) == 0
        mw.on_tool_response("test_tool", {}, "result")
        assert len(mw._buffer) == 0

    def test_auto_save_flush_failure_preserves_buffer(self, chat_store, config_enabled):
        """If store_messages raises, buffer should NOT be cleared."""
        mw = AutoSaveMiddleware(chat_store, config_enabled, session_id="test-session")
        mw.on_tool_call("test_tool", {"query": "test"})
        mw.on_tool_response("test_tool", {"query": "test"}, "result")
        # Buffer was flushed, should be empty
        assert len(mw._buffer) == 0

        # Now test failure case
        mw2 = AutoSaveMiddleware(chat_store, config_enabled, session_id="test-session-2")
        with patch.object(chat_store, "store_messages", side_effect=RuntimeError("DB error")):
            mw2.on_tool_call("fail_tool", {})
            mw2.on_tool_response("fail_tool", {}, "result")
        # Buffer should be preserved after failure
        assert len(mw2._buffer) == 2

    def test_auto_save_respects_config_toggle(self, chat_store, config_disabled):
        """AutoConfig(auto_save=False) should make middleware disabled."""
        mw = AutoSaveMiddleware(chat_store, config_disabled)
        assert mw._enabled is False
        mw.on_tool_call("test", {})
        assert len(mw._buffer) == 0

    def test_auto_save_empty_buffer_flush_is_noop(self, chat_store, config_enabled):
        """Flushing an empty buffer should do nothing."""
        mw = AutoSaveMiddleware(chat_store, config_enabled, session_id="test-session")
        mw._flush()  # Should not raise
        assert len(mw._buffer) == 0


class TestTruncateResult:
    """Tests for _truncate_result helper."""

    def test_truncates_long_string(self):
        """Strings > max_len should be truncated with '...'."""
        result = _truncate_result("a" * 600, max_len=500)
        assert len(result) == 503  # 500 + "..."
        assert result.endswith("...")

    def test_preserves_short_string(self):
        """Strings <= max_len should be unchanged."""
        result = _truncate_result("hello", max_len=500)
        assert result == "hello"

    def test_handles_dict(self):
        """Dicts should be JSON-serialized."""
        result = _truncate_result({"key": "value"}, max_len=500)
        assert '"key": "value"' in result or '"key":"value"' in result

    def test_handles_list(self):
        """Lists should be JSON-serialized."""
        result = _truncate_result([1, 2, 3], max_len=500)
        assert result == "[1, 2, 3]"

    def test_truncates_dict_over_limit(self):
        """Large dicts should be truncated."""
        large = {"data": "x" * 600}
        result = _truncate_result(large, max_len=500)
        assert len(result) == 503
        assert result.endswith("...")
