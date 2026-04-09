"""Tests for the file_graph module — FileNode, FileGraph, and change detection."""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime

import pytest

from context_memory_mcp.file_graph import FileNode


# ---------------------------------------------------------------------------
# FileNode tests (T04)
# ---------------------------------------------------------------------------

class TestFileNode:
    """Tests for the FileNode data class."""

    def test_init_all_attributes(self) -> None:
        """Constructor accepts all 5 attributes."""
        node = FileNode(
            path="/tmp/test.py",
            language="python",
            size_bytes=1024,
            last_modified="2024-01-01T00:00:00+00:00",
            file_hash="abc123",
        )
        assert node.path == "/tmp/test.py"
        assert node.language == "python"
        assert node.size_bytes == 1024
        assert node.last_modified == "2024-01-01T00:00:00+00:00"
        assert node.file_hash == "abc123"

    def test_init_defaults(self) -> None:
        """Constructor defaults for optional attributes."""
        node = FileNode(path="/tmp/test.py")
        assert node.language == "unknown"
        assert node.size_bytes == 0
        assert node.last_modified == ""
        assert node.file_hash == ""

    def test_compute_hash_returns_sha256_hex(self, tmp_path) -> None:
        """compute_hash returns correct SHA-256 hex digest."""
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        result = FileNode.compute_hash(str(f))
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected
        assert len(result) == 64  # SHA-256 hex is 64 chars

    def test_compute_hash_uses_chunked_reads(self, tmp_path) -> None:
        """compute_hash produces same result as single-read hash."""
        f = tmp_path / "big.txt"
        content = "x" * 20000  # Larger than 8KB chunk
        f.write_text(content)
        result = FileNode.compute_hash(str(f))
        expected = hashlib.sha256(content.encode()).hexdigest()
        assert result == expected

    def test_update_from_file_populates_metadata(self, tmp_path) -> None:
        """update_from_file computes correct SHA-256 and populates metadata."""
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        node = FileNode(path=str(f))
        node.update_from_file(str(f))

        assert node.path == os.path.abspath(str(f))
        assert node.size_bytes == len("print('hello')".encode())
        assert node.last_modified != ""
        assert node.file_hash == FileNode.compute_hash(str(f))
        assert len(node.file_hash) == 64

    def test_update_from_file_computes_absolute_path(self, tmp_path) -> None:
        """update_from_file stores absolute path."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        node = FileNode(path="relative/path.py")
        node.update_from_file(str(f))
        assert os.path.isabs(node.path)

    def test_to_dict_returns_serializable_dict(self) -> None:
        """to_dict() returns a dictionary with all fields."""
        node = FileNode(
            path="/path/to/file.py",
            language="python",
            size_bytes=500,
            last_modified="2024-06-15T12:00:00+00:00",
            file_hash="deadbeef",
        )
        d = node.to_dict()
        assert isinstance(d, dict)
        assert d["path"] == "/path/to/file.py"
        assert d["language"] == "python"
        assert d["size_bytes"] == 500
        assert d["last_modified"] == "2024-06-15T12:00:00+00:00"
        assert d["file_hash"] == "deadbeef"

    def test_to_dict_after_update_from_file(self, tmp_path) -> None:
        """to_dict() returns correct data after update_from_file."""
        f = tmp_path / "test.py"
        f.write_text("x = 42")
        node = FileNode(path=str(f))
        node.update_from_file(str(f))
        d = node.to_dict()
        assert d["file_hash"] == FileNode.compute_hash(str(f))
        assert d["size_bytes"] > 0
        assert d["last_modified"] != ""


# ---------------------------------------------------------------------------
# FileGraph tests (T06)
# ---------------------------------------------------------------------------

import networkx as nx

from context_memory_mcp.file_graph import (
    CODE_EXTENSIONS,
    SKIP_DIRS,
    FileGraph,
    get_graph,
    reset_graph,
)


class TestFileGraphInit:
    """Tests for FileGraph initialization."""

    def test_init_creates_digraph(self) -> None:
        """Constructor creates empty NetworkX DiGraph."""
        fg = FileGraph()
        assert isinstance(fg.graph, nx.DiGraph)
        assert fg.graph.number_of_nodes() == 0
        assert fg.graph.number_of_edges() == 0

    def test_init_sets_root_path(self) -> None:
        """Constructor stores absolute root_path."""
        fg = FileGraph(root_path="/tmp/project")
        import os
        assert os.path.isabs(fg.root_path)

    def test_init_empty_hash_index(self) -> None:
        """Constructor initializes empty _hash_index."""
        fg = FileGraph()
        assert fg._hash_index == {}


class TestFileGraphWalkCodeFiles:
    """Tests for _walk_code_files directory walking."""

    def test_walk_skips_skip_dirs(self, tmp_path) -> None:
        """_walk_code_files skips .git, __pycache__, .venv, etc."""
        # Create files in skip dirs
        (tmp_path / ".git" / "config").parent.mkdir(exist_ok=True)
        (tmp_path / ".git" / "config").write_text("[core]")
        (tmp_path / "__pycache__" / "mod.cpython-313.pyc").parent.mkdir(exist_ok=True)
        (tmp_path / "__pycache__" / "mod.cpython-313.pyc").write_text("cache")
        # Create a real Python file
        (tmp_path / "main.py").write_text("x = 1")

        fg = FileGraph()
        files = list(fg._walk_code_files(str(tmp_path)))
        # Should only find main.py
        assert len(files) == 1
        assert files[0].endswith("main.py")

    def test_walk_finds_python_files(self, tmp_path) -> None:
        """_walk_code_files finds .py files in nested directories."""
        (tmp_path / "src" / "pkg").mkdir(parents=True)
        (tmp_path / "src" / "main.py").write_text("import pkg.mod")
        (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
        (tmp_path / "src" / "pkg" / "mod.py").write_text("x = 1")

        fg = FileGraph()
        files = list(fg._walk_code_files(str(tmp_path)))
        assert len(files) == 3

    def test_walk_filters_extensions(self, tmp_path) -> None:
        """_walk_code_files only returns supported extensions."""
        (tmp_path / "main.py").write_text("x = 1")
        (tmp_path / "app.js").write_text("let x = 1;")
        (tmp_path / "readme.md").write_text("# README")
        (tmp_path / "data.json").write_text("{}")

        fg = FileGraph()
        files = list(fg._walk_code_files(str(tmp_path)))
        assert len(files) == 2  # .py and .js only


class TestFileGraphBuildGraph:
    """Tests for build_graph."""

    def test_build_graph_returns_summary_dict(self, tmp_path) -> None:
        """build_graph returns dict with file_count, node_count, edge_count, built_at."""
        (tmp_path / "main.py").write_text("import os\n\ndef main():\n    pass\n")
        fg = FileGraph()
        result = fg.build_graph(str(tmp_path))
        assert "file_count" in result
        assert "node_count" in result
        assert "edge_count" in result
        assert "built_at" in result

    def test_build_graph_creates_nodes(self, tmp_path) -> None:
        """build_graph creates nodes for files and symbols."""
        (tmp_path / "main.py").write_text("import os\n\ndef main():\n    pass\n")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        assert fg.graph.number_of_nodes() > 0

    def test_build_graph_populates_hash_index(self, tmp_path) -> None:
        """build_graph populates _hash_index with SHA-256 hashes."""
        (tmp_path / "main.py").write_text("x = 1")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        assert len(fg._hash_index) > 0
        for entry in fg._hash_index.values():
            assert "hash" in entry
            assert len(entry["hash"]) == 64  # SHA-256 hex

    def test_build_graph_creates_file_nodes(self, tmp_path) -> None:
        """build_graph creates file-level nodes with correct attributes."""
        (tmp_path / "main.py").write_text("x = 1")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        main_path = str(tmp_path / "main.py")
        assert main_path in fg.graph
        node_data = fg.graph.nodes[main_path]
        assert node_data["kind"] == "file"
        assert node_data["language"] == "python"

    def test_build_graph_creates_symbol_nodes(self, tmp_path) -> None:
        """build_graph creates symbol nodes for classes/functions."""
        code = '''
class MyClass:
    def greet(self):
        pass

def helper():
    pass
'''
        (tmp_path / "sample.py").write_text(code)
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        # Should have nodes for MyClass, MyClass.greet, helper
        node_kinds = {fg.graph.nodes[n].get("kind") for n in fg.graph.nodes()}
        assert "class" in node_kinds
        assert "method" in node_kinds
        assert "function" in node_kinds

    def test_build_graph_creates_contains_edges(self, tmp_path) -> None:
        """build_graph creates CONTAINS edges for class→method hierarchy."""
        code = '''
class MyClass:
    def method(self):
        pass
'''
        (tmp_path / "sample.py").write_text(code)
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        edge_types = {data.get("edge_type") for _, _, data in fg.graph.edges(data=True)}
        assert "CONTAINS" in edge_types

    def test_build_graph_detects_tested_by(self, tmp_path) -> None:
        """build_graph creates TESTED_BY edges for test_*.py files."""
        (tmp_path / "foo.py").write_text("def do_thing(): pass")
        (tmp_path / "test_foo.py").write_text("def test_do_thing(): pass")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        edge_types = {data.get("edge_type") for _, _, data in fg.graph.edges(data=True)}
        assert "TESTED_BY" in edge_types

    def test_build_graph_empty_directory(self, tmp_path) -> None:
        """build_graph handles empty directories gracefully."""
        fg = FileGraph()
        result = fg.build_graph(str(tmp_path))
        assert result["file_count"] == 0
        assert result["node_count"] == 0
        assert result["edge_count"] == 0


class TestFileGraphQueries:
    """Tests for graph query methods."""

    def test_add_file(self) -> None:
        """add_file adds a node to the graph."""
        fg = FileGraph()
        node = FileNode(path="/test/file.py", language="python", size_bytes=100)
        fg.add_file(node)
        assert "/test/file.py" in fg.graph

    def test_add_dependency(self) -> None:
        """add_dependency adds an edge with type."""
        fg = FileGraph()
        fg.graph.add_node("/a.py")
        fg.graph.add_node("/b.py")
        fg.add_dependency("/a.py", "/b.py", "IMPORTS_FROM")
        assert fg.graph.has_edge("/a.py", "/b.py")
        edge_data = fg.graph.get_edge_data("/a.py", "/b.py")
        assert edge_data["edge_type"] == "IMPORTS_FROM"

    def test_get_dependencies_empty(self) -> None:
        """get_dependencies returns empty for unknown file."""
        fg = FileGraph()
        assert fg.get_dependencies("/nonexistent.py") == []

    def test_get_dependents_empty(self) -> None:
        """get_dependents returns empty for unknown file."""
        fg = FileGraph()
        assert fg.get_dependents("/nonexistent.py") == []

    def test_get_impact_set_empty(self) -> None:
        """get_impact_set returns empty for unknown files."""
        fg = FileGraph()
        assert fg.get_impact_set(["/nonexistent.py"]) == set()


class TestGraphSingleton:
    """Tests for module-level singleton pattern."""

    def test_get_graph_creates_instance(self) -> None:
        """get_graph creates FileGraph on first call."""
        reset_graph()
        g = get_graph()
        assert isinstance(g, FileGraph)

    def test_get_graph_returns_same_instance(self) -> None:
        """get_graph returns the same singleton instance."""
        reset_graph()
        g1 = get_graph()
        g2 = get_graph()
        assert g1 is g2

    def test_reset_graph_clears_singleton(self) -> None:
        """reset_graph clears the singleton."""
        reset_graph()
        g1 = get_graph()
        reset_graph()
        g2 = get_graph()
        assert g1 is not g2
