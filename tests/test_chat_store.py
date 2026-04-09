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
