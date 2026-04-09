"""Comprehensive pytest suite for ChatStore CRUD, filtering, and session isolation."""

from __future__ import annotations

import pytest
import shutil
import os

from context_memory_mcp.chat_store import ChatStore


@pytest.fixture()
def store(tmp_path):
    """Create a ChatStore instance with a temporary path."""
    chroma_path = str(tmp_path / "chromadb")
    s = ChatStore(chroma_path=chroma_path)
    yield s
    s.close()
    if os.path.exists(chroma_path):
        shutil.rmtree(chroma_path)


class TestInit:
    def test_creates_directory(self, tmp_path):
        chroma_path = str(tmp_path / "test_chromadb")
        store = ChatStore(chroma_path=chroma_path)
        assert os.path.exists(chroma_path)
        store.close()
        shutil.rmtree(chroma_path)

    def test_close_no_error(self, store):
        store.close()  # Should not raise


class TestStoreMessages:
    def test_store_returns_correct_dict(self, store):
        result = store.store_messages(
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
            session_id="sess-001",
        )
        assert result["stored"] == 2
        assert result["session_id"] == "sess-001"

    def test_auto_generates_session_id(self, store):
        result = store.store_messages(
            [{"role": "user", "content": "Test"}],
        )
        assert result["stored"] == 1
        assert len(result["session_id"]) == 36  # UUID4 length
        # Verify it's a valid UUID
        import uuid
        uuid.UUID(result["session_id"])

    def test_stores_with_custom_timestamp(self, store):
        result = store.store_messages(
            [
                {
                    "role": "user",
                    "content": "Timestamped message",
                    "timestamp": "2024-01-15T10:00:00+00:00",
                }
            ],
            session_id="sess-ts",
        )
        assert result["stored"] == 1

    def test_empty_messages(self, store):
        result = store.store_messages([], session_id="sess-empty")
        assert result["stored"] == 0


class TestQueryMessages:
    def _setup_session(self, store, session_id):
        """Helper to store messages for a session."""
        store.store_messages(
            [
                {"role": "user", "content": "How do I use Python?"},
                {"role": "assistant", "content": "Python is a programming language"},
                {"role": "user", "content": "What about JavaScript?"},
                {"role": "assistant", "content": "JavaScript is for web development"},
            ],
            session_id=session_id,
        )

    def test_query_returns_results(self, store):
        self._setup_session(store, "q-sess-1")
        results = store.query_messages("programming language", top_k=3)
        assert len(results) > 0
        assert all(
            "content" in r and "role" in r and "distance" in r
            for r in results
        )

    def test_query_respects_top_k(self, store):
        self._setup_session(store, "q-sess-2")
        results = store.query_messages("language", top_k=2)
        assert len(results) <= 2

    def test_query_filters_by_session(self, store):
        self._setup_session(store, "q-sess-a")
        self._setup_session(store, "q-sess-b")
        # Store different content in session B
        store.store_messages(
            [{"role": "user", "content": "Unique session B content"}],
            session_id="q-sess-b",
        )
        results = store.query_messages(
            "Unique session B", top_k=5, session_id="q-sess-a"
        )
        # Results should only be from session A
        for r in results:
            assert r["session_id"] == "q-sess-a"

    def test_query_filters_by_role(self, store):
        self._setup_session(store, "q-sess-role")
        results = store.query_messages(
            "language", top_k=10, session_id="q-sess-role", role="user"
        )
        for r in results:
            assert r["role"] == "user"

    def test_query_with_date_filtering(self, store):
        store.store_messages(
            [
                {
                    "role": "user",
                    "content": "January message",
                    "timestamp": "2024-01-15T10:00:00+00:00",
                },
                {
                    "role": "user",
                    "content": "March message",
                    "timestamp": "2024-03-15T10:00:00+00:00",
                },
                {
                    "role": "user",
                    "content": "June message",
                    "timestamp": "2024-06-15T10:00:00+00:00",
                },
            ],
            session_id="q-sess-date",
        )
        results = store.query_messages(
            "message",
            top_k=10,
            session_id="q-sess-date",
            date_from="2024-02-01T00:00:00+00:00",
            date_to="2024-04-30T23:59:59+00:00",
        )
        # Should only include March message
        for r in results:
            assert r["timestamp"] >= "2024-02-01T00:00:00+00:00"
            assert r["timestamp"] <= "2024-04-30T23:59:59+00:00"

    def test_query_similarity_score(self, store):
        self._setup_session(store, "q-sess-sim")
        results = store.query_messages("programming", top_k=3)
        for r in results:
            assert "similarity" in r
            assert 0 <= r["similarity"] <= 1
            assert r["similarity"] == round(1 - r["distance"], 4)


class TestSessionIsolation:
    def test_no_cross_contamination(self, store):
        store.store_messages(
            [{"role": "user", "content": "Secret from session A"}],
            session_id="isolation-a",
        )
        results = store.query_messages(
            "Secret", top_k=10, session_id="isolation-b"
        )
        assert len(results) == 0


class TestListSessions:
    def test_returns_empty_list(self, store):
        sessions = store.list_sessions()
        assert sessions == []

    def test_returns_unique_sorted_sessions(self, store):
        store.store_messages(
            [{"role": "user", "content": "msg"}], session_id="z-sess"
        )
        store.store_messages(
            [{"role": "user", "content": "msg"}], session_id="a-sess"
        )
        store.store_messages(
            [{"role": "user", "content": "msg"}], session_id="a-sess"
        )
        sessions = store.list_sessions()
        assert sessions == ["a-sess", "z-sess"]


class TestDeleteSession:
    def test_deletes_all_messages(self, store):
        store.store_messages(
            [
                {"role": "user", "content": "msg 1"},
                {"role": "assistant", "content": "msg 2"},
                {"role": "user", "content": "msg 3"},
            ],
            session_id="del-sess",
        )
        deleted = store.delete_session("del-sess")
        assert deleted == 3
        sessions = store.list_sessions()
        assert "del-sess" not in sessions

    def test_delete_nonexistent_returns_zero(self, store):
        deleted = store.delete_session("nonexistent")
        assert deleted == 0

    def test_delete_only_target_session(self, store):
        store.store_messages(
            [{"role": "user", "content": "keep me"}],
            session_id="keep-sess",
        )
        store.store_messages(
            [{"role": "user", "content": "delete me"}],
            session_id="del-sess",
        )
        store.delete_session("del-sess")
        sessions = store.list_sessions()
        assert "keep-sess" in sessions
        assert "del-sess" not in sessions


class TestBuildWhere:
    def test_no_filters_returns_none(self, store):
        assert store._build_where() is None

    def test_session_only(self, store):
        result = store._build_where(session_id="abc")
        assert result == {"session_id": "abc"}

    def test_role_only(self, store):
        result = store._build_where(role="user")
        assert result == {"role": "user"}

    def test_both_filters(self, store):
        result = store._build_where(session_id="abc", role="user")
        assert "$and" in result
        assert {"session_id": "abc"} in result["$and"]
        assert {"role": "user"} in result["$and"]


class TestAutoSessionId:
    def test_uuid_is_valid(self, store):
        import uuid
        result = store.store_messages(
            [{"role": "user", "content": "test"}],
        )
        session_id = result["session_id"]
        parsed = uuid.UUID(session_id)  # Should not raise
        assert str(parsed) == session_id

    def test_multiple_auto_ids_are_unique(self, store):
        ids = []
        for _ in range(5):
            result = store.store_messages(
                [{"role": "user", "content": f"msg {_}"}],
            )
            ids.append(result["session_id"])
        assert len(set(ids)) == 5
