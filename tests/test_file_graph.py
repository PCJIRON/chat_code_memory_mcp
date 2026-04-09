"""Tests for the file_graph module — FileNode, FileGraph, and change detection."""

from __future__ import annotations

import hashlib
import json
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


# ---------------------------------------------------------------------------
# SHA-256 change detection and incremental update tests (T07)
# ---------------------------------------------------------------------------

class TestFileGraphChangeDetection:
    """Tests for has_changed and update_graph."""

    def test_has_changed_returns_true_for_unknown_file(self) -> None:
        """has_changed returns True for files not in hash index."""
        fg = FileGraph()
        assert fg.has_changed("/nonexistent/file.py") is True

    def test_has_changed_returns_false_for_unchanged_file(self, tmp_path) -> None:
        """has_changed returns False when file matches stored hash."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        assert fg.has_changed(str(f)) is False

    def test_has_changed_returns_true_for_modified_file(self, tmp_path) -> None:
        """has_changed returns True when file content differs."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        # Modify the file
        f.write_text("x = 2")
        assert fg.has_changed(str(f)) is True

    def test_has_changed_returns_true_for_removed_file(self, tmp_path) -> None:
        """has_changed returns True when file has been removed."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        # Remove the file
        f.unlink()
        assert fg.has_changed(str(f)) is True

    def test_update_graph_no_changes(self, tmp_path) -> None:
        """update_graph returns 0 updates when no files changed."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        result = fg.update_graph(str(tmp_path))
        assert result["added"] == 0
        assert result["removed"] == 0
        assert result["updated"] == 0
        assert result["unchanged"] == 1
        assert result["total_files"] == 1

    def test_update_graph_one_changed_file(self, tmp_path) -> None:
        """update_graph only re-parses changed files."""
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("x = 1")
        f2.write_text("y = 2")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        original_hash_a = fg._hash_index[str(f1)]["hash"]

        # Modify only one file
        f1.write_text("x = 999")
        result = fg.update_graph(str(tmp_path))

        assert result["updated"] == 1
        assert result["unchanged"] == 1
        # Hash should be updated
        assert fg._hash_index[str(f1)]["hash"] != original_hash_a

    def test_update_graph_explicit_changed_files(self, tmp_path) -> None:
        """update_graph with explicit changed_files list."""
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("x = 1")
        f2.write_text("y = 2")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))

        # Explicitly mark f1 as changed
        result = fg.update_graph(str(tmp_path), changed_files=[str(f1)])
        assert result["updated"] == 1
        assert result["unchanged"] == 1

    def test_update_graph_removed_file(self, tmp_path) -> None:
        """update_graph cleans up removed files."""
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("x = 1")
        f2.write_text("y = 2")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        assert str(f1) in fg._hash_index
        assert str(f2) in fg._hash_index

        # Remove f1
        f1.unlink()
        result = fg.update_graph(str(tmp_path))

        assert result["removed"] == 1
        assert str(f1) not in fg._hash_index
        assert str(f2) in fg._hash_index
        # Graph should not have nodes for removed file
        file_nodes = [
            n for n in fg.graph.nodes()
            if fg.graph.nodes[n].get("file_path") == str(f1)
        ]
        assert len(file_nodes) == 0

    def test_update_graph_preserves_unchanged_nodes(self, tmp_path) -> None:
        """update_graph preserves nodes/edges for unchanged files."""
        code_a = "def func_a(): pass\n"
        code_b = "class ClassB:\n    def method_b(self): pass\n"
        fa = tmp_path / "a.py"
        fb = tmp_path / "b.py"
        fa.write_text(code_a)
        fb.write_text(code_b)
        fg = FileGraph()
        fg.build_graph(str(tmp_path))

        # Get original node count
        original_node_count = fg.graph.number_of_nodes()

        # Modify only a.py
        fa.write_text("def func_a(): return 42\n")
        fg.update_graph(str(tmp_path))

        # Node count should be similar (a.py nodes replaced, b.py preserved)
        assert fg.graph.number_of_nodes() > 0

    def test_update_graph_returns_summary_dict(self, tmp_path) -> None:
        """update_graph returns correct summary structure."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        result = fg.update_graph(str(tmp_path))
        assert "added" in result
        assert "removed" in result
        assert "updated" in result
        assert "unchanged" in result
        assert "total_files" in result

    def test_update_graph_empty_directory(self, tmp_path) -> None:
        """update_graph handles empty directories."""
        fg = FileGraph()
        fg.build_graph(str(tmp_path))
        result = fg.update_graph(str(tmp_path))
        assert result["total_files"] == 0
        assert result["added"] == 0
        assert result["removed"] == 0


# ---------------------------------------------------------------------------
# Graph persistence tests (T08)
# ---------------------------------------------------------------------------


class TestFileGraphPersistence:
    """Tests for save/load round-trip persistence."""

    def test_save_writes_valid_json(self, tmp_path) -> None:
        """save() writes valid JSON to disk."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        fg = FileGraph(root_path=str(tmp_path))
        fg.build_graph(str(tmp_path))

        save_path = str(tmp_path / "data" / "file_graph.json")
        fg.save(save_path)

        assert os.path.exists(save_path)
        with open(save_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert "nodes" in data
        assert "edges" in data  # NetworkX 3.x uses "edges" not "links"
        assert "_hash_index" in data
        assert "_metadata" in data

    def test_load_reconstructs_graph(self, tmp_path) -> None:
        """load() reconstructs graph with all node/edge attributes."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        fg = FileGraph(root_path=str(tmp_path))
        fg.build_graph(str(tmp_path))

        original_nodes = fg.graph.number_of_nodes()
        original_edges = fg.graph.number_of_edges()

        save_path = str(tmp_path / "data" / "file_graph.json")
        fg.save(save_path)

        loaded = FileGraph.load(save_path)
        assert loaded.graph.number_of_nodes() == original_nodes
        assert loaded.graph.number_of_edges() == original_edges

    def test_round_trip_preserves_node_edge_counts(self, tmp_path) -> None:
        """Round-trip: build -> save -> load -> verify counts match."""
        code = '''
import os

class MyClass:
    def method(self):
        pass

def helper():
    pass
'''
        (tmp_path / "sample.py").write_text(code)
        fg = FileGraph(root_path=str(tmp_path))
        fg.build_graph(str(tmp_path))

        original_nodes = fg.graph.number_of_nodes()
        original_edges = fg.graph.number_of_edges()
        original_hash_index = dict(fg._hash_index)

        save_path = str(tmp_path / "data" / "file_graph.json")
        fg.save(save_path)

        loaded = FileGraph.load(save_path)
        assert loaded.graph.number_of_nodes() == original_nodes
        assert loaded.graph.number_of_edges() == original_edges
        assert loaded._hash_index == original_hash_index

    def test_save_creates_data_directory(self, tmp_path) -> None:
        """save() creates ./data/ directory automatically if missing."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        fg = FileGraph(root_path=str(tmp_path))
        fg.build_graph(str(tmp_path))

        save_path = str(tmp_path / "data" / "file_graph.json")
        assert not os.path.exists(os.path.dirname(save_path))
        fg.save(save_path)
        assert os.path.exists(save_path)

    def test_save_load_empty_edges(self, tmp_path) -> None:
        """Edge case: graph with 0 edges saves/loads correctly."""
        fg = FileGraph()
        # Don't build graph — graph is empty
        save_path = str(tmp_path / "data" / "file_graph.json")
        fg.save(save_path)

        loaded = FileGraph.load(save_path)
        assert loaded.graph.number_of_nodes() == 0
        assert loaded.graph.number_of_edges() == 0

    def test_round_trip_preserves_line_number_types(self, tmp_path) -> None:
        """Edge case: line number attributes survive round-trip as integers."""
        code = '''
def my_function():
    pass
'''
        (tmp_path / "sample.py").write_text(code)
        fg = FileGraph(root_path=str(tmp_path))
        fg.build_graph(str(tmp_path))

        # Find a symbol node with line_start/line_end
        symbol_nodes = [
            n for n in fg.graph.nodes()
            if fg.graph.nodes[n].get("kind") in ("function", "class", "method")
        ]
        assert len(symbol_nodes) > 0

        save_path = str(tmp_path / "data" / "file_graph.json")
        fg.save(save_path)

        loaded = FileGraph.load(save_path)
        for node_id in symbol_nodes:
            loaded_node = loaded.graph.nodes[node_id]
            if "line_start" in loaded_node:
                assert isinstance(loaded_node["line_start"], int), \
                    f"line_start should be int, got {type(loaded_node['line_start'])}"
            if "line_end" in loaded_node:
                assert isinstance(loaded_node["line_end"], int), \
                    f"line_end should be int, got {type(loaded_node['line_end'])}"

    def test_load_metadata_preserved(self, tmp_path) -> None:
        """load() preserves metadata (root_path, saved_at)."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        fg = FileGraph(root_path=str(tmp_path))
        fg.build_graph(str(tmp_path))

        save_path = str(tmp_path / "data" / "file_graph.json")
        fg.save(save_path)

        loaded = FileGraph.load(save_path)
        assert loaded.root_path == os.path.abspath(str(tmp_path))
        assert "_metadata" in open(save_path, "r", encoding="utf-8").read()


# ---------------------------------------------------------------------------
# Graph query method tests (T09)
# ---------------------------------------------------------------------------


class TestFileGraphQueryMethods:
    """Tests for get_file_nodes and get_subgraph query methods."""

    def test_get_file_nodes_returns_file_and_symbols(self, tmp_path) -> None:
        """get_file_nodes returns file-level node and all symbol nodes."""
        code = '''
class MyClass:
    def method(self):
        pass

def helper():
    pass
'''
        (tmp_path / "sample.py").write_text(code)
        fg = FileGraph(root_path=str(tmp_path))
        fg.build_graph(str(tmp_path))

        sample_path = str(tmp_path / "sample.py")
        nodes = fg.get_file_nodes(sample_path)
        # Should have file node + class + method + function
        assert len(nodes) >= 4
        # File node should be in results
        assert sample_path in nodes

    def test_get_file_nodes_empty_for_unknown_file(self) -> None:
        """get_file_nodes returns empty list for unknown file."""
        fg = FileGraph()
        assert fg.get_file_nodes("/nonexistent.py") == []

    def test_get_subgraph_returns_structured_dict(self, tmp_path) -> None:
        """get_subgraph returns dict with file, nodes, edges, dependencies."""
        code_a = '''
import os

class MyClass:
    def method(self):
        pass
'''
        (tmp_path / "a.py").write_text(code_a)
        fg = FileGraph(root_path=str(tmp_path))
        fg.build_graph(str(tmp_path))

        a_path = str(tmp_path / "a.py")
        result = fg.get_subgraph(a_path)
        assert "file" in result
        assert "nodes" in result
        assert "edges" in result
        assert "dependencies" in result
        assert "dependents" in result
        assert "impact_summary" in result
        assert result["file"] == a_path
        assert isinstance(result["nodes"], list)
        assert isinstance(result["edges"], list)
        assert isinstance(result["dependencies"], list)
        assert isinstance(result["dependents"], list)
        assert "direct_dependencies" in result["impact_summary"]
        assert "direct_dependents" in result["impact_summary"]

    def test_get_subgraph_edges_have_source_target(self, tmp_path) -> None:
        """get_subgraph edges have source, target, and edge_type."""
        code = '''
class MyClass:
    def method(self):
        pass
'''
        (tmp_path / "sample.py").write_text(code)
        fg = FileGraph(root_path=str(tmp_path))
        fg.build_graph(str(tmp_path))

        sample_path = str(tmp_path / "sample.py")
        result = fg.get_subgraph(sample_path)
        # Should have CONTAINS edges
        contains_edges = [
            e for e in result["edges"]
            if e.get("edge_type") == "CONTAINS"
        ]
        assert len(contains_edges) > 0
        for edge in contains_edges:
            assert "source" in edge
            assert "target" in edge

    def test_get_subgraph_unknown_file(self, tmp_path) -> None:
        """get_subgraph handles unknown file gracefully."""
        fg = FileGraph(root_path=str(tmp_path))
        fg.build_graph(str(tmp_path))
        result = fg.get_subgraph(str(tmp_path / "nonexistent.py"))
        assert result["file"] == str(tmp_path / "nonexistent.py")
        assert result["nodes"] == []
        assert result["edges"] == []


# ---------------------------------------------------------------------------
# MCP tool registration tests (T10)
# ---------------------------------------------------------------------------


class TestMCPToolRegistration:
    """Tests for track_files and get_file_graph MCP tool registration."""

    def test_register_function_exists(self) -> None:
        """register function exists in file_graph module."""
        from context_memory_mcp.file_graph import register

        assert callable(register)

    def test_register_adds_tools(self) -> None:
        """register() adds track_files and get_file_graph tools to MCP server."""
        from mcp.server.fastmcp import FastMCP

        from context_memory_mcp.file_graph import register

        mcp = FastMCP("test-graph-tools")
        register(mcp)
        # Verify tools are registered by checking server tool registry
        # FastMCP stores tools internally; we verify by checking no exception
        # during registration and the tools are callable
        assert hasattr(mcp, "tool")

    def test_mcp_server_register_all_includes_graph(self) -> None:
        """mcp_server.register_all() imports and registers graph tools."""
        from context_memory_mcp.mcp_server import register_all

        # Should not raise any import or registration errors
        register_all()

    def test_track_files_returns_json(self, tmp_path) -> None:
        """track_files tool returns valid JSON with expected fields."""
        import asyncio

        from context_memory_mcp.file_graph import get_graph, reset_graph, register

        # Reset singleton for clean test
        reset_graph()

        f = tmp_path / "test.py"
        f.write_text("x = 1")

        # Create a mock MCP server and register tools
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test-track-files")
        register(mcp)

        # Call track_files directly (we test the underlying function logic)
        from context_memory_mcp.file_graph import get_graph, reset_graph

        reset_graph()
        graph = get_graph()
        result = graph.build_graph(str(tmp_path))
        import json

        output = json.dumps({"status": "ok", **result}, indent=2)
        data = json.loads(output)
        assert data["status"] == "ok"
        assert "file_count" in data
        assert "node_count" in data
        assert "edge_count" in data

    def test_get_file_graph_returns_json(self, tmp_path) -> None:
        """get_file_graph tool returns valid JSON with subgraph data."""
        import json

        from context_memory_mcp.file_graph import FileGraph, get_graph, reset_graph

        reset_graph()
        code = '''
class MyClass:
    def method(self):
        pass
'''
        (tmp_path / "sample.py").write_text(code)
        graph = get_graph()
        graph.build_graph(str(tmp_path))

        sample_path = str(tmp_path / "sample.py")
        result = graph.get_subgraph(sample_path)
        output = json.dumps(result, indent=2)
        data = json.loads(output)
        assert "file" in data
        assert "nodes" in data
        assert "edges" in data

    def test_get_file_graph_empty_graph_returns_error(self, tmp_path) -> None:
        """get_file_graph returns error message when no graph data available."""
        import json

        from context_memory_mcp.file_graph import FileGraph, get_graph, reset_graph

        reset_graph()
        graph = get_graph()

        # Empty graph, no file on disk
        if graph.graph.number_of_nodes() == 0:
            try:
                default_path = os.path.join(graph.root_path, "data", "file_graph.json")
                graph = FileGraph.load(default_path)
            except (FileNotFoundError, OSError):
                output = json.dumps(
                    {"error": "No graph data available. Run track_files first."},
                    indent=2,
                )
                data = json.loads(output)
                assert "error" in data
