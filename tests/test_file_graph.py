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
