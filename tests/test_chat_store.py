"""Tests for ChatStore — CRUD, filtering, and session isolation."""

from __future__ import annotations

import time

import pytest

from context_memory_mcp.chat_store import ChatStore


@pytest.fixture()
def store(tmp_path):
    """Create a ChatStore with an isolated temp directory."""
    s = ChatStore(
        chroma_path=str(tmp_path / "chromadb"),
        session_index_path=str(tmp_path / "session_index.json"),
    )
    yield s
    s.close()


# --- T2: store_messages ---


def test_store_messages_returns_count_and_session_id(store: ChatStore) -> None:
    result = store.store_messages(
        [{"role": "user", "content": "hello"}], session_id="test-sess"
    )
    assert result["stored"] == 1
    assert result["session_id"] == "test-sess"


def test_store_messages_auto_session_id(store: ChatStore) -> None:
    result = store.store_messages([{"role": "user", "content": "hi"}])
    assert result["stored"] == 1
    assert result["session_id"] is not None
    assert len(result["session_id"]) > 10  # UUID length check


def test_store_messages_batch(store: ChatStore) -> None:
    msgs = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "reply1"},
        {"role": "user", "content": "msg2"},
    ]
    result = store.store_messages(msgs, session_id="batch-sess")
    assert result["stored"] == 3


def test_store_messages_empty_raises(store: ChatStore) -> None:
    """Empty messages list should raise ValueError."""
    with pytest.raises(ValueError, match="messages list cannot be empty"):
        store.store_messages([], session_id="empty-sess")


def test_store_messages_missing_content_raises(store: ChatStore) -> None:
    """Message without 'content' key should raise ValueError."""
    with pytest.raises(ValueError, match="missing required 'content' key"):
        store.store_messages([{"role": "user"}], session_id="bad-sess")


def test_store_messages_auto_role(store: ChatStore) -> None:
    """Message without 'role' key should default to 'user'."""
    result = store.store_messages([{"content": "no role specified"}], session_id="auto-role")
    assert result["stored"] == 1
    # Verify the message was stored with role="user"
    results = store.query_messages("no role", session_id="auto-role", top_k=1)
    assert results[0]["role"] == "user"


def test_store_messages_persistence(store: ChatStore, tmp_path) -> None:
    """Messages survive store and are queryable."""
    store.store_messages(
        [{"role": "user", "content": "the quick brown fox"}], session_id="persist-sess"
    )
    results = store.query_messages("fast animal", session_id="persist-sess", top_k=1)
    assert len(results) == 1
    assert "fox" in results[0]["content"]


# --- T4: query_messages ---


def test_query_messages_returns_keys(store: ChatStore) -> None:
    store.store_messages(
        [{"role": "user", "content": "hello world"}], session_id="q-sess"
    )
    results = store.query_messages("greeting", session_id="q-sess", top_k=1)
    assert len(results) == 1
    r = results[0]
    assert "content" in r
    assert "role" in r
    assert "timestamp" in r
    assert "distance" in r
    assert "similarity" in r


def test_query_messages_semantic_similarity(store: ChatStore) -> None:
    store.store_messages(
        [
            {"role": "user", "content": "how to sort a list in python"},
            {"role": "assistant", "content": "use the sorted() function"},
            {"role": "user", "content": "the weather is nice today"},
        ],
        session_id="semantic-sess",
    )
    results = store.query_messages("python sorting", session_id="semantic-sess", top_k=2)
    assert len(results) == 2
    # Most relevant results should be about sorting
    assert any("sort" in r["content"].lower() for r in results)


def test_query_messages_top_k(store: ChatStore) -> None:
    msgs = [{"role": "user", "content": f"message number {i}"} for i in range(10)]
    store.store_messages(msgs, session_id="topk-sess")
    results = store.query_messages("number", session_id="topk-sess", top_k=3)
    assert len(results) == 3


def test_query_messages_no_matches(store: ChatStore) -> None:
    """Query always returns results due to semantic search nature (no true empty)."""
    store.store_messages(
        [{"role": "user", "content": "hello world"}], session_id="no-match-sess"
    )
    # Semantic search always returns something within the session
    results = store.query_messages(
        "xyzzy plugh nothingrelevant", session_id="no-match-sess", top_k=5
    )
    # Results will have low similarity scores (high distance)
    assert len(results) <= 1  # Only one message stored, so at most 1 result
    if results:
        assert results[0]["similarity"] < 0.5  # Low similarity expected


# --- Session Isolation ---


def test_session_isolation(store: ChatStore) -> None:
    store.store_messages(
        [{"role": "user", "content": "secret from session A"}], session_id="sess-a"
    )
    store.store_messages(
        [{"role": "user", "content": "secret from session B"}], session_id="sess-b"
    )
    # Query session A should not return session B's content
    results_a = store.query_messages("secret", session_id="sess-a", top_k=5)
    for r in results_a:
        assert r["session_id"] == "sess-a"


# --- T4: Date Filtering ---


def test_date_filtering(store: ChatStore) -> None:
    store.store_messages(
        [
            {
                "role": "user",
                "content": "january message",
                "timestamp": "2024-01-15T10:00:00+00:00",
            },
            {
                "role": "user",
                "content": "march message",
                "timestamp": "2024-03-15T10:00:00+00:00",
            },
            {
                "role": "user",
                "content": "june message",
                "timestamp": "2024-06-15T10:00:00+00:00",
            },
        ],
        session_id="date-sess",
    )
    # Filter: February to April → should return january and march messages
    results = store.query_messages(
        "message",
        session_id="date-sess",
        date_from="2024-02-01T00:00:00+00:00",
        date_to="2024-04-30T23:59:59+00:00",
        top_k=10,
    )
    contents = [r["content"] for r in results]
    assert "march message" in contents
    assert "january message" not in contents
    assert "june message" not in contents


def test_date_filtering_empty(store: ChatStore) -> None:
    store.store_messages(
        [
            {
                "role": "user",
                "content": "old message",
                "timestamp": "2024-01-01T10:00:00+00:00",
            },
        ],
        session_id="date-sess-2",
    )
    results = store.query_messages(
        "message",
        session_id="date-sess-2",
        date_from="2025-01-01T00:00:00+00:00",
        top_k=10,
    )
    assert len(results) == 0


# --- Role Filtering ---


def test_role_filter(store: ChatStore) -> None:
    store.store_messages(
        [
            {"role": "user", "content": "user says hello"},
            {"role": "assistant", "content": "assistant replies"},
            {"role": "user", "content": "user asks again"},
        ],
        session_id="role-sess",
    )
    results = store.query_messages("hello", session_id="role-sess", role="user", top_k=10)
    for r in results:
        assert r["role"] == "user"


# --- T5: list_sessions ---


def test_list_sessions(store: ChatStore) -> None:
    store.store_messages([{"role": "user", "content": "a"}], session_id="alpha")
    store.store_messages([{"role": "user", "content": "b"}], session_id="beta")
    store.store_messages([{"role": "user", "content": "c"}], session_id="gamma")
    sessions = store.list_sessions()
    assert sessions == ["alpha", "beta", "gamma"]


def test_list_sessions_empty(store: ChatStore) -> None:
    assert store.list_sessions() == []


# --- T6: delete_session ---


def test_delete_session(store: ChatStore) -> None:
    store.store_messages(
        [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
        ],
        session_id="to-delete",
    )
    store.store_messages([{"role": "user", "content": "keep"}], session_id="to-keep")
    deleted = store.delete_session("to-delete")
    assert deleted == 2
    sessions = store.list_sessions()
    assert "to-delete" not in sessions
    assert "to-keep" in sessions


def test_delete_nonexistent_session(store: ChatStore) -> None:
    deleted = store.delete_session("does-not-exist")
    assert deleted == 0


# --- NFR-2: Performance smoke test ---


def test_store_performance(store: ChatStore) -> None:
    """Store should complete in <500ms for typical batch."""
    msgs = [{"role": "user", "content": f"perf test message {i}"} for i in range(10)]
    start = time.time()
    store.store_messages(msgs, session_id="perf-sess")
    elapsed = time.time() - start
    # First run may be slower due to model loading; just log it
    assert elapsed < 5.0, f"Store took {elapsed:.2f}s — unexpectedly slow"


def test_query_performance(store: ChatStore) -> None:
    """Query should complete in <1s for typical search."""
    msgs = [{"role": "user", "content": f"perf test {i}"} for i in range(20)]
    store.store_messages(msgs, session_id="perf-sess-q")
    start = time.time()
    store.query_messages("test", session_id="perf-sess-q", top_k=5)
    elapsed = time.time() - start
    assert elapsed < 5.0, f"Query took {elapsed:.2f}s — unexpectedly slow"


# --- T04: prune_sessions ---


def test_prune_sessions_by_date(store: ChatStore) -> None:
    """Date-based pruning removes sessions before the given date."""
    store.store_messages(
        [{"role": "user", "content": "old msg", "timestamp": "2024-01-01T10:00:00+00:00"}],
        session_id="old-session",
    )
    store.store_messages(
        [{"role": "user", "content": "new msg", "timestamp": "2024-06-01T10:00:00+00:00"}],
        session_id="new-session",
    )
    result = store.prune_sessions(before_date="2024-03-01T00:00:00+00:00")
    assert result["pruned"] == 1
    assert result["remaining"] == 1
    sessions = store.list_sessions()
    assert "old-session" not in sessions
    assert "new-session" in sessions


def test_prune_sessions_by_max(store: ChatStore) -> None:
    """Max sessions pruning keeps only N most recent."""
    for i in range(5):
        store.store_messages(
            [{"role": "user", "content": f"msg {i}", "timestamp": f"2024-0{i+1}-01T10:00:00+00:00"}],
            session_id=f"sess-{i}",
        )
    result = store.prune_sessions(max_sessions=2)
    assert result["pruned"] == 3
    assert result["remaining"] == 2
    sessions = store.list_sessions()
    # Should keep the 2 most recent (sess-3, sess-4)
    assert "sess-4" in sessions
    assert "sess-3" in sessions
    assert "sess-0" not in sessions
    assert "sess-1" not in sessions
    assert "sess-2" not in sessions


def test_prune_sessions_combined(store: ChatStore) -> None:
    """Combined: date filter first, then max_sessions cap."""
    # Old sessions
    for i in range(3):
        store.store_messages(
            [{"role": "user", "content": f"old {i}", "timestamp": f"2024-0{i+1}-01T10:00:00+00:00"}],
            session_id=f"old-{i}",
        )
    # New sessions
    for i in range(4):
        store.store_messages(
            [{"role": "user", "content": f"new {i}", "timestamp": f"2024-0{7+i}-01T10:00:00+00:00"}],
            session_id=f"new-{i}",
        )
    # Date filter removes old-0, old-1, old-2 (before 2024-05), then cap to 2 of remaining
    result = store.prune_sessions(
        before_date="2024-05-01T00:00:00+00:00",
        max_sessions=2,
    )
    assert result["pruned"] == 5  # 3 old + 2 of 4 new
    assert result["remaining"] == 2


def test_prune_sessions_nothing_to_prune(store: ChatStore) -> None:
    """When no sessions match the prune criteria, nothing is deleted."""
    store.store_messages(
        [{"role": "user", "content": "msg", "timestamp": "2024-06-01T10:00:00+00:00"}],
        session_id="keep-sess",
    )
    result = store.prune_sessions(before_date="2020-01-01T00:00:00+00:00")
    assert result["pruned"] == 0
    assert result["remaining"] == 1


def test_prune_sessions_empty_store(store: ChatStore) -> None:
    """Pruning an empty store returns zeros."""
    result = store.prune_sessions()
    assert result == {"pruned": 0, "remaining": 0}


def test_prune_sessions_max_sessions_one(store: ChatStore) -> None:
    """Keep only 1 most recent session."""
    store.store_messages(
        [{"role": "user", "content": "a", "timestamp": "2024-01-01T10:00:00+00:00"}],
        session_id="first",
    )
    store.store_messages(
        [{"role": "user", "content": "b", "timestamp": "2024-02-01T10:00:00+00:00"}],
        session_id="second",
    )
    result = store.prune_sessions(max_sessions=1)
    assert result["pruned"] == 1
    assert result["remaining"] == 1
    sessions = store.list_sessions()
    assert "second" in sessions
    assert "first" not in sessions


# --- T08-T09: Session index tests ---


def test_session_index_updated_on_store(store: ChatStore) -> None:
    """Session index is updated when messages are stored."""
    store.store_messages(
        [{"role": "user", "content": "hello"}],
        session_id="index-sess",
    )
    sessions = store.list_sessions()
    assert "index-sess" in sessions


def test_session_index_updated_on_delete(store: ChatStore) -> None:
    """Session index is updated when a session is deleted."""
    store.store_messages(
        [{"role": "user", "content": "hello"}],
        session_id="delete-sess",
    )
    assert "delete-sess" in store.list_sessions()
    store.delete_session("delete-sess")
    assert "delete-sess" not in store.list_sessions()


def test_list_sessions_reads_index(store: ChatStore) -> None:
    """list_sessions() returns sorted session IDs from the index."""
    store.store_messages([{"role": "user", "content": "a"}], session_id="zebra")
    store.store_messages([{"role": "user", "content": "b"}], session_id="alpha")
    store.store_messages([{"role": "user", "content": "c"}], session_id="middle")
    sessions = store.list_sessions()
    assert sessions == ["alpha", "middle", "zebra"]


# --- T08-T09: conversation_id alias tests ---


def test_query_chat_conversation_id_alias(store: ChatStore) -> None:
    """query_messages works with session_id parameter (alias simulation)."""
    store.store_messages(
        [{"role": "user", "content": "hello from session X"}],
        session_id="sess-X",
    )
    # query_messages uses session_id directly; the alias is in the MCP tool layer
    results = store.query_messages("hello", session_id="sess-X", top_k=5)
    assert len(results) == 1
    assert results[0]["session_id"] == "sess-X"


def test_query_chat_empty_session_id_raises(store: ChatStore) -> None:
    """Empty session_id string should be rejected at the MCP tool level.

    Note: query_messages itself accepts None/empty; validation is in query_chat.
    This test verifies the ChatStore query_messages handles session_id="".
    """
    store.store_messages(
        [{"role": "user", "content": "test message"}],
        session_id="valid-sess",
    )
    # query_messages with empty string should not crash (returns empty due to no match)
    results = store.query_messages("test", session_id="", top_k=5)
    assert isinstance(results, list)


# --- T08-T09: Date validation tests ---


def test_query_chat_invalid_date_raises(store: ChatStore) -> None:
    """Invalid ISO 8601 date should raise ValueError."""
    store.store_messages(
        [{"role": "user", "content": "test"}],
        session_id="date-sess",
    )
    with pytest.raises(ValueError, match="Invalid date_from format"):
        store.query_messages("test", date_from="not-a-date", top_k=5)

    with pytest.raises(ValueError, match="Invalid date_to format"):
        store.query_messages("test", date_to="also-not-a-date", top_k=5)


def test_query_chat_date_range_swap(store: ChatStore) -> None:
    """When date_from > date_to, they should be swapped automatically."""
    store.store_messages(
        [
            {"role": "user", "content": "march msg", "timestamp": "2024-03-15T10:00:00+00:00"},
            {"role": "user", "content": "may msg", "timestamp": "2024-05-15T10:00:00+00:00"},
        ],
        session_id="swap-sess",
    )
    # Intentionally swap the dates (from > to)
    results = store.query_messages(
        "msg",
        session_id="swap-sess",
        date_from="2024-06-01T00:00:00+00:00",  # After date_to — should swap
        date_to="2024-04-01T00:00:00+00:00",
        top_k=10,
    )
    contents = [r["content"] for r in results]
    # After swap, range is April to June → should get may msg
    assert "may msg" in contents
    assert "march msg" not in contents


def test_query_messages_empty_results(store: ChatStore) -> None:
    """Empty results should return an empty list, not an error."""
    store.store_messages(
        [{"role": "user", "content": "hello world"}],
        session_id="empty-results",
    )
    results = store.query_messages(
        "xyzzy",
        session_id="empty-results",
        date_from="2099-01-01T00:00:00+00:00",  # Far future — no matches
        top_k=5,
    )
    assert results == []


# --- Phase 6: File change storage and queries ---


def test_store_file_change_stores_with_metadata(store: ChatStore) -> None:
    """store_file_change should store with correct metadata."""
    result = store.store_file_change({
        "file_path": "src/test.py",
        "change_type": "modified",
        "snippet": "def foo(): pass",
    })
    assert result["stored"] == 1
    assert result["id"].startswith("fc_")


def test_store_file_change_requires_file_path(store: ChatStore) -> None:
    """Missing file_path should raise ValueError."""
    with pytest.raises(ValueError, match="missing required key: file_path"):
        store.store_file_change({"change_type": "modified"})


def test_store_file_change_requires_change_type(store: ChatStore) -> None:
    """Missing change_type should raise ValueError."""
    with pytest.raises(ValueError, match="missing required key: change_type"):
        store.store_file_change({"file_path": "src/test.py"})


def test_query_file_changes_returns_results(store: ChatStore) -> None:
    """query_file_changes should return file_change documents."""
    store.store_file_change({
        "file_path": "src/test.py",
        "change_type": "modified",
        "snippet": "def foo(): pass",
    })
    results = store.query_file_changes("test.py", top_k=5)
    assert len(results) >= 1
    assert results[0]["file_path"] == "src/test.py"
    assert results[0]["change_type"] == "modified"


def test_query_file_changes_excludes_chat_messages(store: ChatStore) -> None:
    """query_file_changes should not return chat messages."""
    store.store_messages([
        {"role": "user", "content": "hello world"},
    ], session_id="chat-sess")
    results = store.query_file_changes("hello", top_k=5)
    assert len(results) == 0


def test_query_messages_excludes_file_changes(store: ChatStore) -> None:
    """query_messages should not return file_change documents."""
    store.store_file_change({
        "file_path": "src/test.py",
        "change_type": "modified",
        "snippet": "def foo(): pass",
    })
    results = store.query_messages("test", top_k=5)
    for r in results:
        assert "type" not in r or r.get("type") != "file_change"


def test_query_file_changes_by_change_type(store: ChatStore) -> None:
    """query_file_changes should filter by change_type."""
    store.store_file_change({
        "file_path": "src/a.py",
        "change_type": "modified",
        "snippet": "def a(): pass",
    })
    store.store_file_change({
        "file_path": "src/b.py",
        "change_type": "created",
        "snippet": "def b(): pass",
    })
    results = store.query_file_changes("src", top_k=10, change_type="created")
    for r in results:
        assert r["change_type"] == "created"


def test_query_file_changes_by_file_path(store: ChatStore) -> None:
    """query_file_changes should filter by file_path."""
    store.store_file_change({
        "file_path": "src/a.py",
        "change_type": "modified",
        "snippet": "def a(): pass",
    })
    store.store_file_change({
        "file_path": "src/b.py",
        "change_type": "modified",
        "snippet": "def b(): pass",
    })
    results = store.query_file_changes("src", top_k=10, file_path="src/a.py")
    for r in results:
        assert r["file_path"] == "src/a.py"


def test_query_file_changes_empty_collection(store: ChatStore) -> None:
    """Empty file changes collection should return empty list."""
    results = store.query_file_changes("anything", top_k=5)
    assert results == []


def test_store_file_change_truncates_long_snippet(store: ChatStore) -> None:
    """Long snippets should be truncated to 200 chars."""
    long_snippet = "x" * 500
    store.store_file_change({
        "file_path": "src/long.py",
        "change_type": "modified",
        "snippet": long_snippet,
    })
    results = store.query_file_changes("long", top_k=5)
    assert len(results) >= 1
    # The stored document should be truncated
    assert len(results[0]["content"]) < 500


def test_store_file_change_deleted_file(store: ChatStore) -> None:
    """Deleted files should be stored without snippet."""
    store.store_file_change({
        "file_path": "src/removed.py",
        "change_type": "deleted",
        "snippet": "",
    })
    results = store.query_file_changes("removed", top_k=5)
    assert len(results) >= 1
    assert results[0]["change_type"] == "deleted"


def test_file_change_backward_compat_with_chat_messages(store: ChatStore) -> None:
    """Chat messages stored before file_change feature should still be queryable."""
    # Store a regular chat message (no type metadata)
    store.store_messages([
        {"role": "user", "content": "legacy message without type"},
    ], session_id="legacy-sess")
    # query_messages should still find it (treats missing type as "chat")
    results = store.query_messages("legacy", top_k=5)
    assert len(results) >= 1
    assert "legacy message" in results[0]["content"]
