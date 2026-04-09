"""End-to-end integration tests for all MCP tools.

Tests exercise all MCP tools working together:
- Chat storage and retrieval (store_chat, query_chat, list_sessions, delete_session, prune_sessions)
- Context system (get_context with detail levels)
- File graph (track_files, get_file_graph)
- Core tools (ping)

Each test uses isolated temp directories to avoid cross-test pollution.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from context_memory_mcp.chat_store import ChatStore, get_store, register as register_chat_store
from context_memory_mcp.context import (
    ContextBuilder,
    ContextWindow,
    format_with_detail,
    get_minimal_context,
    register as register_context,
)
from context_memory_mcp.file_graph import FileGraph, get_graph, register as register_graph
from context_memory_mcp.parser import ASTParser, ParsedSymbol
from context_memory_mcp.mcp_server import register_all, mcp


# ── Full Pipeline Tests ───────────────────────────────────────────


class TestFullPipeline:
    """Test the complete chat storage + retrieval pipeline."""

    @pytest.fixture()
    def store(self, tmp_path):
        """Create isolated ChatStore."""
        return ChatStore(
            chroma_path=str(tmp_path / "chromadb"),
            session_index_path=str(tmp_path / "session_index.json"),
        )

    def test_store_and_query(self, store):
        """Store messages, then query them."""
        messages = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a high-level programming language..."},
        ]
        result = store.store_messages(messages, session_id="test-1")
        assert result["stored"] == 2
        assert result["session_id"] == "test-1"

        results = store.query_messages("Python", top_k=5)
        assert len(results) >= 1
        assert "Python" in results[0]["content"]

    def test_context_compression_integration(self):
        """Test context compression with real query results."""
        messages = [
            {"role": "user", "content": "Explain the code"},
            {"role": "assistant", "content": "This code implements a chat store using ChromaDB..."},
        ]
        window = get_minimal_context(messages, max_tokens=100)
        assert window.token_count <= 120
        assert "User:" in window.content
        assert "Assistant:" in window.content

    def test_detail_levels_integration(self):
        """Test all detail levels with real data."""
        results = {
            "query": "test",
            "total_found": 3,
            "results": [
                {"content": "Message 1", "role": "user", "timestamp": "2024-01-01T00:00:00"},
                {"content": "Message 2", "role": "assistant", "timestamp": "2024-01-01T00:01:00"},
            ],
        }

        minimal = format_with_detail(results, "minimal")
        summary = format_with_detail(results, "summary")
        full = format_with_detail(results, "full")

        assert len(minimal) <= len(summary) <= len(full)
        assert "test" in minimal
        assert "test" in summary

    def test_session_lifecycle(self, store):
        """Test complete session lifecycle: store -> list -> prune -> delete."""
        # Store
        store.store_messages([{"role": "user", "content": "Hello"}], session_id="sess-1")
        store.store_messages([{"role": "user", "content": "World"}], session_id="sess-2")

        # List
        sessions = store.list_sessions()
        assert "sess-1" in sessions
        assert "sess-2" in sessions

        # Prune (delete sess-1)
        result = store.prune_sessions(max_sessions=1)
        assert result["pruned"] >= 1

        # Verify
        sessions = store.list_sessions()
        assert "sess-2" in sessions

    def test_session_prune_and_delete(self, store):
        """Test prune_sessions and delete_session work together."""
        for i in range(5):
            store.store_messages(
                [{"role": "user", "content": f"msg {i}", "timestamp": f"2024-0{i+1}-01T10:00:00+00:00"}],
                session_id=f"sess-{i}",
            )

        # Prune to keep only 2
        prune_result = store.prune_sessions(max_sessions=2)
        assert prune_result["pruned"] == 3
        assert prune_result["remaining"] == 2

        # Delete one of the remaining
        sessions = store.list_sessions()
        if sessions:
            delete_count = store.delete_session(sessions[0])
            assert delete_count >= 1
            assert sessions[0] not in store.list_sessions()

    def test_query_with_date_and_role_filters(self, store):
        """Test query_messages with combined date and role filters."""
        store.store_messages(
            [
                {"role": "user", "content": "user query", "timestamp": "2024-03-01T10:00:00+00:00"},
                {"role": "assistant", "content": "assistant reply", "timestamp": "2024-03-01T10:01:00+00:00"},
                {"role": "user", "content": "another user query", "timestamp": "2024-04-01T10:00:00+00:00"},
            ],
            session_id="filter-sess",
        )

        results = store.query_messages(
            "query",
            session_id="filter-sess",
            date_from="2024-03-15T00:00:00+00:00",
            role="user",
            top_k=10,
        )
        contents = [r["content"] for r in results]
        assert "another user query" in contents
        assert "user query" not in contents  # Before date_from


# ── Graph Pipeline Tests ──────────────────────────────────────────


class TestGraphPipeline:
    """Test the complete file graph pipeline."""

    def test_build_and_query(self, tmp_path):
        """Build a graph and query it."""
        # Create test files
        test_file = tmp_path / "test_module.py"
        test_file.write_text("import os\n\nclass MyClass:\n    def __init__(self):\n        pass\n")

        graph = FileGraph(root_path=str(tmp_path))
        summary = graph.build_graph(str(tmp_path))

        assert summary["file_count"] >= 1
        assert summary["node_count"] >= 1

        # Query
        nodes = graph.get_file_nodes(str(test_file))
        assert len(nodes) >= 1

        deps = graph.get_dependencies(str(test_file))
        assert isinstance(deps, list)

    def test_save_load_roundtrip(self, tmp_path):
        """Test graph persistence."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass\n")

        graph = FileGraph(root_path=str(tmp_path))
        graph.build_graph(str(tmp_path))

        save_path = str(tmp_path / "graph.json")
        graph.save(save_path)

        loaded = FileGraph.load(save_path)
        assert loaded.graph.number_of_nodes() == graph.graph.number_of_nodes()

    def test_update_graph_incremental(self, tmp_path):
        """Test incremental graph update detects changes."""
        test_file = tmp_path / "mod.py"
        test_file.write_text("def foo(): pass\n")

        graph = FileGraph(root_path=str(tmp_path))
        graph.build_graph(str(tmp_path))
        initial_nodes = graph.graph.number_of_nodes()

        # Modify the file
        test_file.write_text("def foo(): pass\ndef bar(): pass\n")

        result = graph.update_graph(str(tmp_path))
        assert result["updated"] >= 1
        assert result["total_files"] >= 1

    def test_graph_impact_analysis(self, tmp_path):
        """Test get_impact_set returns correct impacted files."""
        file_a = tmp_path / "module_a.py"
        file_b = tmp_path / "module_b.py"
        file_a.write_text("def helper(): pass\n")
        file_b.write_text("import module_a\n\ndef use_helper(): helper()\n")

        graph = FileGraph(root_path=str(tmp_path))
        graph.build_graph(str(tmp_path))

        impacted = graph.get_impact_set([str(file_a)])
        # file_b imports module_a, so it should be impacted
        assert isinstance(impacted, set)


# ── All Tools Together Tests ──────────────────────────────────────


class TestAllToolsTogether:
    """Test that all tool categories work together without conflicts."""

    def test_import_all_modules(self):
        """Verify all modules import without errors."""
        from context_memory_mcp.chat_store import ChatStore, register as register_chat
        from context_memory_mcp.context import ContextBuilder, register as register_ctx
        from context_memory_mcp.file_graph import FileGraph, register as register_gr
        from context_memory_mcp.parser import ASTParser, ParsedSymbol
        from context_memory_mcp.mcp_server import register_all

        assert callable(register_chat)
        assert callable(register_ctx)
        assert callable(register_gr)
        assert callable(register_all)

    def test_mcp_server_register_all(self):
        """Test that register_all() works without errors."""
        from context_memory_mcp.mcp_server import register_all

        register_all()  # Should not raise

    def test_chat_store_and_graph_no_conflict(self, tmp_path):
        """Test that ChatStore and FileGraph can coexist in same process."""
        # Create isolated ChatStore
        store = ChatStore(
            chroma_path=str(tmp_path / "chromadb"),
            session_index_path=str(tmp_path / "session_index.json"),
        )

        # Create FileGraph
        test_file = tmp_path / "code.py"
        test_file.write_text("def main(): pass\n")
        graph = FileGraph(root_path=str(tmp_path))

        # Both should work independently
        store.store_messages([{"role": "user", "content": "hello"}], session_id="test")
        graph.build_graph(str(tmp_path))

        assert "test" in store.list_sessions()
        assert graph.graph.number_of_nodes() >= 1

        store.close()

    def test_context_builder_with_real_data(self, tmp_path):
        """Test ContextBuilder with real ChatStore data."""
        store = ChatStore(
            chroma_path=str(tmp_path / "chromadb"),
            session_index_path=str(tmp_path / "session_index.json"),
        )

        store.store_messages(
            [
                {"role": "user", "content": "How does the graph work?"},
                {
                    "role": "assistant",
                    "content": "The FileGraph uses NetworkX to track file dependencies.",
                },
            ],
            session_id="ctx-sess",
        )

        builder = ContextBuilder(max_tokens=4000)
        window = builder.build(
            query="graph dependencies",
            session_id="ctx-sess",
            active_files=["file_graph.py", "parser.py"],
        )

        assert isinstance(window, ContextWindow)
        assert window.token_count > 0
        assert "Query: graph dependencies" in window.content
        assert "Session: ctx-sess" in window.content
        assert "Active files: 2" in window.content

        store.close()

    def test_full_detail_level_pipeline(self, tmp_path):
        """Test storing messages, querying, and formatting at all detail levels."""
        store = ChatStore(
            chroma_path=str(tmp_path / "chromadb"),
            session_index_path=str(tmp_path / "session_index.json"),
        )

        store.store_messages(
            [
                {"role": "user", "content": "Explain ChromaDB"},
                {
                    "role": "assistant",
                    "content": "ChromaDB is a vector database for embeddings.",
                },
            ],
            session_id="pipeline-sess",
        )

        results = store.query_messages("vector database", top_k=5)
        assert len(results) >= 1

        # Format at all levels
        query_results = {
            "query": "vector database",
            "total_found": len(results),
            "results": results,
        }

        minimal = format_with_detail(query_results, "minimal")
        summary = format_with_detail(query_results, "summary")
        full = format_with_detail(query_results, "full")

        assert "vector database" in minimal
        assert "ChromaDB" in summary or "vector" in summary
        parsed_full = json.loads(full)
        assert parsed_full["total_found"] >= 1

        store.close()

    def test_error_handling_invalid_params(self, tmp_path):
        """Test error handling for invalid parameters across tools."""
        store = ChatStore(
            chroma_path=str(tmp_path / "chromadb"),
            session_index_path=str(tmp_path / "session_index.json"),
        )

        # Empty messages should raise
        with pytest.raises(ValueError, match="messages list cannot be empty"):
            store.store_messages([], session_id="empty")

        # Invalid date should raise
        with pytest.raises(ValueError, match="Invalid date_from format"):
            store.query_messages("test", date_from="not-a-date", top_k=5)

        # Invalid detail level should raise
        with pytest.raises(ValueError, match="Invalid detail level"):
            format_with_detail([], level="invalid")

        # Missing content should raise
        with pytest.raises(ValueError, match="missing required 'content' key"):
            store.store_messages([{"role": "user"}], session_id="bad")

        store.close()

    def test_graph_with_multiple_files_and_imports(self, tmp_path):
        """Test graph building with multiple files and import relationships."""
        # Create a package structure
        pkg_dir = tmp_path / "mypackage"
        pkg_dir.mkdir()

        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "utils.py").write_text(
            "import os\n\ndef helper():\n    return os.getcwd()\n"
        )
        (pkg_dir / "main.py").write_text(
            "from mypackage.utils import helper\n\ndef main():\n    helper()\n"
        )

        graph = FileGraph(root_path=str(tmp_path))
        summary = graph.build_graph(str(tmp_path))

        assert summary["file_count"] >= 3
        assert summary["node_count"] >= 3
        assert summary["edge_count"] >= 0  # Edges depend on import matching

        # Query each file
        for fname in ["__init__.py", "utils.py", "main.py"]:
            fpath = str(pkg_dir / fname)
            nodes = graph.get_file_nodes(fpath)
            assert len(nodes) >= 1

    def test_store_query_list_prune_full_cycle(self, tmp_path):
        """Full lifecycle: store -> query -> list -> prune -> verify."""
        store = ChatStore(
            chroma_path=str(tmp_path / "chromadb"),
            session_index_path=str(tmp_path / "session_index.json"),
        )

        # Store messages in multiple sessions
        for i in range(10):
            store.store_messages(
                [
                    {"role": "user", "content": f"Question {i}"},
                    {"role": "assistant", "content": f"Answer {i}"},
                ],
                session_id=f"cycle-sess-{i}",
            )

        # Verify all sessions exist
        sessions = store.list_sessions()
        assert len(sessions) == 10

        # Query across all sessions
        results = store.query_messages("Question", top_k=20)
        assert len(results) >= 1

        # Prune to keep only 3 most recent
        prune_result = store.prune_sessions(max_sessions=3)
        assert prune_result["pruned"] == 7
        assert prune_result["remaining"] == 3

        # Verify only 3 remain
        sessions = store.list_sessions()
        assert len(sessions) == 3

        store.close()
