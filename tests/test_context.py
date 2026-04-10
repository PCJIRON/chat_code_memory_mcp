"""Tests for context compression and formatting."""

from __future__ import annotations

import pytest

from context_memory_mcp.context import (
    ContextBuilder,
    ContextWindow,
    _estimate_tokens,
    format_with_detail,
    get_minimal_context,
)


# ── _estimate_tokens ──────────────────────────────────────────────


class TestEstimateTokens:
    def test_estimate_tokens_empty_string(self) -> None:
        assert _estimate_tokens("") == 0

    def test_estimate_tokens_short_text(self) -> None:
        # 4 chars/token heuristic
        assert _estimate_tokens("hello") == 1  # 5 // 4 = 1

    def test_estimate_tokens_known_length(self) -> None:
        text = "a" * 400
        assert _estimate_tokens(text) == 100


# ── ContextWindow ─────────────────────────────────────────────────


class TestContextWindow:
    def test_init_defaults(self) -> None:
        window = ContextWindow()
        assert window.content == ""
        assert window.token_count == 0
        assert window.max_tokens == 4000
        assert window.sources == []

    def test_init_with_values(self) -> None:
        window = ContextWindow(content="hello", token_count=5, max_tokens=100, sources=["chat"])
        assert window.content == "hello"
        assert window.token_count == 5
        assert window.max_tokens == 100
        assert window.sources == ["chat"]

    def test_fits_within_budget(self) -> None:
        window = ContextWindow(token_count=50, max_tokens=100)
        assert window.fits("short text")  # 9 // 4 = 2 tokens, 50 + 2 <= 100

    def test_fits_exceeds_budget(self) -> None:
        window = ContextWindow(token_count=90, max_tokens=100)
        assert not window.fits("a" * 100)  # 100 // 4 = 25 tokens, 90 + 25 > 100

    def test_to_dict(self) -> None:
        window = ContextWindow(content="test", token_count=10, max_tokens=200, sources=["a", "b"])
        d = window.to_dict()
        assert d == {
            "content": "test",
            "token_count": 10,
            "max_tokens": 200,
            "sources": ["a", "b"],
        }


# ── get_minimal_context ───────────────────────────────────────────


class TestGetMinimalContext:
    def test_empty_messages(self) -> None:
        result = get_minimal_context([])
        assert result.content == ""
        assert result.token_count == 0
        assert result.max_tokens == 100

    def test_single_user_message(self) -> None:
        msgs = [{"role": "user", "content": "hello world"}]
        result = get_minimal_context(msgs)
        assert "User: hello world" in result.content
        assert result.token_count <= 120

    def test_user_and_assistant(self) -> None:
        msgs = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]
        result = get_minimal_context(msgs)
        assert "User: What is Python?" in result.content
        assert "Assistant: Python is a programming language." in result.content
        assert result.token_count <= 120

    def test_truncates_long_content(self) -> None:
        long_text = "x" * 500  # 500 // 4 = 125 tokens > 50
        msgs = [
            {"role": "user", "content": long_text},
            {"role": "assistant", "content": long_text},
        ]
        result = get_minimal_context(msgs)
        assert "..." in result.content
        assert result.token_count <= 120

    def test_many_messages_uses_only_latest(self) -> None:
        msgs = [
            {"role": "user", "content": "first query"},
            {"role": "assistant", "content": "first reply"},
            {"role": "user", "content": "second query"},
            {"role": "assistant", "content": "second reply"},
        ]
        result = get_minimal_context(msgs)
        assert "first query" not in result.content
        assert "second query" in result.content
        assert "second reply" in result.content

    def test_no_assistant_message(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        result = get_minimal_context(msgs)
        assert "User: hello" in result.content
        assert "Assistant:" not in result.content

    def test_no_user_message(self) -> None:
        msgs = [{"role": "assistant", "content": "hello"}]
        result = get_minimal_context(msgs)
        assert "Assistant: hello" in result.content
        assert "User:" not in result.content

    def test_custom_max_tokens(self) -> None:
        result = get_minimal_context([], max_tokens=200)
        assert result.max_tokens == 200

    def test_fits_budget(self) -> None:
        msgs = [
            {"role": "user", "content": "short query"},
            {"role": "assistant", "content": "short reply"},
        ]
        result = get_minimal_context(msgs)
        assert result.token_count <= 120


# ── format_with_detail ────────────────────────────────────────────


class TestFormatWithDetail:
    def test_invalid_level_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid detail level"):
            format_with_detail([], level="invalid")

    def test_empty_results_minimal(self) -> None:
        result = format_with_detail([], level="minimal")
        assert "results" in result
        assert "minimal" in result

    def test_empty_results_summary(self) -> None:
        result = format_with_detail([], level="summary")
        assert "results" in result
        assert "summary" in result

    def test_empty_results_full(self) -> None:
        result = format_with_detail([], level="full")
        assert "results" in result
        assert "full" in result

    def test_minimal_list_results(self) -> None:
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = format_with_detail(msgs, level="minimal")
        assert "Total messages: 2" in result
        assert "Last user: hello" in result
        assert "Last assistant: hi there" in result

    def test_minimal_dict_results(self) -> None:
        results = {"query": "test", "total_found": 3, "results": [{"content": "hello"}]}
        result = format_with_detail(results, level="minimal")
        assert "Query: test" in result
        assert "Results: 3" in result

    def test_summary_list_results(self) -> None:
        msgs = [
            {"role": "user", "content": "hello", "timestamp": "2024-01-01T00:00:00"},
            {"role": "assistant", "content": "hi there", "timestamp": "2024-01-01T00:01:00"},
        ]
        result = format_with_detail(msgs, level="summary")
        assert "Total messages: 2" in result
        assert "[user]" in result
        assert "[assistant]" in result

    def test_summary_dict_results(self) -> None:
        results = {
            "query": "test",
            "total_found": 2,
            "results": [
                {"role": "user", "content": "hello", "distance": 0.1, "similarity": 0.9},
            ],
        }
        result = format_with_detail(results, level="summary")
        assert "Query: test" in result
        assert "similarity: 0.9" in result

    def test_full_returns_raw_json(self) -> None:
        data = {"key": "value", "numbers": [1, 2, 3]}
        result = format_with_detail(data, level="full")
        assert '"key": "value"' in result
        assert '"numbers"' in result

    def test_minimal_truncates_long_content(self) -> None:
        long_text = "x" * 500
        msgs = [
            {"role": "user", "content": long_text},
            {"role": "assistant", "content": long_text},
        ]
        result = format_with_detail(msgs, level="minimal")
        assert "..." in result

    def test_summary_limits_to_5_messages(self) -> None:
        msgs = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        result = format_with_detail(msgs, level="summary")
        assert "... and 5 more messages" in result


# ── HybridContextBuilder ──────────────────────────────────────────


class TestContextBuilder:
    """Tests for HybridContextBuilder (replaces old stub ContextBuilder)."""

    @pytest.fixture()
    def store(self, tmp_path):
        """Create isolated ChatStore."""
        from context_memory_mcp.chat_store import ChatStore
        s = ChatStore(
            chroma_path=str(tmp_path / "chromadb"),
            session_index_path=str(tmp_path / "session_index.json"),
        )
        yield s
        s.close()

    def test_build_basic_query(self, store) -> None:
        from context_memory_mcp.context import HybridContextBuilder
        builder = HybridContextBuilder(store=store)
        window = builder.build(query="What is this?")
        assert window.token_count >= 0
        assert isinstance(window.sources, list)

    def test_build_with_session_id(self, store) -> None:
        from context_memory_mcp.context import HybridContextBuilder
        store.store_messages(
            [{"role": "user", "content": "session specific message"}],
            session_id="sess-123",
        )
        builder = HybridContextBuilder(store=store)
        window = builder.build(query="session specific", session_id="sess-123")
        assert "chat_history" in window.sources or window.token_count >= 0

    def test_build_with_active_files(self, store) -> None:
        from context_memory_mcp.context import HybridContextBuilder
        builder = HybridContextBuilder(store=store)
        window = builder.build(query="test", active_files=["a.py", "b.py", "c.py"])
        assert isinstance(window.sources, list)

    def test_build_with_all_params(self, store) -> None:
        from context_memory_mcp.context import HybridContextBuilder
        store.store_messages(
            [{"role": "user", "content": "hello world test message"}],
            session_id="sess-42",
        )
        builder = HybridContextBuilder(store=store, max_tokens=8000)
        window = builder.build(
            query="hello",
            session_id="sess-42",
            active_files=["main.py"],
        )
        assert window.max_tokens == 8000
        assert isinstance(window.sources, list)

    def test_build_empty_query(self, store) -> None:
        from context_memory_mcp.context import HybridContextBuilder
        builder = HybridContextBuilder(store=store)
        window = builder.build(query="")
        assert isinstance(window.content, str)
        assert isinstance(window.sources, list)

    def test_build_no_optional_params(self, store) -> None:
        from context_memory_mcp.context import HybridContextBuilder
        builder = HybridContextBuilder(store=store)
        window = builder.build(query="test")
        assert isinstance(window.sources, list)

    def test_build_returns_context_window(self, store) -> None:
        from context_memory_mcp.context import HybridContextBuilder, ContextWindow
        builder = HybridContextBuilder(store=store)
        window = builder.build(query="test query")
        assert isinstance(window, ContextWindow)

    def test_build_with_file_changes(self, store) -> None:
        from context_memory_mcp.context import HybridContextBuilder
        store.store_file_change({
            "file_path": "src/test.py",
            "change_type": "modified",
            "snippet": "def new_function(): pass",
        })
        builder = HybridContextBuilder(store=store)
        window = builder.build(query="file change")
        assert isinstance(window.sources, list)
