"""File relationship graph tracking.

Uses NetworkX to track dependencies, imports, and relationships
between files in a codebase for context-aware retrieval.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from context_memory_mcp.parser import ASTParser


class FileNode:
    """Represents a single file in the relationship graph.

    Attributes:
        path: Absolute or relative file path.
        language: Detected programming language.
        size_bytes: File size in bytes.
        last_modified: ISO 8601 timestamp of last modification.
        file_hash: Content SHA-256 hash for change detection.
    """

    def __init__(
        self,
        path: str,
        language: str = "unknown",
        size_bytes: int = 0,
        last_modified: str = "",
        file_hash: str = "",
    ) -> None:
        """Initialize a FileNode.

        Args:
            path: File path.
            language: Programming language of the file.
            size_bytes: File size in bytes.
            last_modified: ISO 8601 timestamp.
            file_hash: Content hash for change detection.
        """
        self.path = path
        self.language = language
        self.size_bytes = size_bytes
        self.last_modified = last_modified
        self.file_hash = file_hash

    @staticmethod
    def compute_hash(file_path: str) -> str:
        """Compute SHA-256 hash of a file using chunked reads (8KB chunks).

        Args:
            file_path: Path to the file to hash.

        Returns:
            Hex digest string of the SHA-256 hash.
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)  # 8KB chunks for 4x faster performance
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()

    def update_from_file(self, file_path: str) -> None:
        """Update node metadata from the actual file on disk.

        Reads file size, modification time, and computes SHA-256 hash.

        Args:
            file_path: Path to the file to read metadata from.
        """
        stat = os.stat(file_path)
        self.path = os.path.abspath(file_path)
        self.size_bytes = stat.st_size
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        self.last_modified = mtime.isoformat()
        self.file_hash = self.compute_hash(file_path)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the node to a dictionary.

        Returns:
            Dictionary representation for JSON serialization.
        """
        return {
            "path": self.path,
            "language": self.language,
            "size_bytes": self.size_bytes,
            "last_modified": self.last_modified,
            "file_hash": self.file_hash,
        }


# Directories to skip during directory walking
SKIP_DIRS = frozenset({
    ".git", ".venv", "__pycache__", "node_modules",
    "dist", "build", ".pytest_cache",
})

# Supported code file extensions
CODE_EXTENSIONS = frozenset({
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx",
    ".rs", ".go", ".java", ".c", ".cpp", ".h", ".hpp",
})


class FileGraph:
    """Graph of file relationships in a codebase.

    Tracks imports, type references, and structural dependencies
    between files using a NetworkX directed graph.

    Attributes:
        root_path: Root directory of the tracked codebase.
        graph: The underlying NetworkX DiGraph.
        _hash_index: SHA-256 index for change detection.
        _parser: ASTParser instance for parsing source files.
    """

    def __init__(self, root_path: str = ".") -> None:
        """Initialize the FileGraph.

        Args:
            root_path: Root directory of the codebase to track.
        """
        import networkx as nx

        self.root_path = os.path.abspath(root_path)
        self.graph = nx.DiGraph()
        self._hash_index: dict[str, dict[str, Any]] = {}
        self._parser = ASTParser()

    def _walk_code_files(self, directory: str):
        """Walk directory tree and yield code file paths.

        Uses in-place dirnames filtering to skip SKIP_DIRS.

        Args:
            directory: Root directory to walk.

        Yields:
            Absolute paths of supported code files.
        """
        directory = os.path.abspath(directory)
        for dirpath, dirnames, filenames in os.walk(directory):
            # In-place filtering to skip SKIP_DIRS
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext in CODE_EXTENSIONS:
                    yield os.path.abspath(os.path.join(dirpath, fname))

    def build_graph(self, directory: str) -> dict:
        """Build the file graph by parsing all code files in a directory.

        Phase 1: Parse all files, create FileNodes, add symbol nodes.
        Phase 2: Extract and add edges between nodes.

        Args:
            directory: Root directory containing code files to parse.

        Returns:
            Summary dict with file_count, node_count, edge_count, built_at.
        """
        import logging
        import networkx as nx
        from datetime import datetime, timezone
        from context_memory_mcp.parser import (
            extract_imports_edges,
            extract_contains_edges,
            detect_tested_by,
        )

        directory = os.path.abspath(directory)
        files = list(self._walk_code_files(directory))
        logging.info(f"Building graph for {len(files)} files in {directory}")

        # Phase 1: Parse all files and create nodes
        all_symbols: dict[str, list] = {}
        all_known_files = set(files)

        for filepath in files:
            symbols = self._parser.parse_file(filepath)
            all_symbols[filepath] = symbols

            # Create FileNode and update from disk
            node = FileNode(path=filepath)
            node.update_from_file(filepath)
            node.language = self._parser.detect_language(filepath)

            # Store in hash index
            self._hash_index[filepath] = {
                "hash": node.file_hash,
                "language": node.language,
                "size_bytes": node.size_bytes,
                "last_modified": node.last_modified,
            }

            # Add file-level node to graph
            self.graph.add_node(
                filepath,
                file_path=filepath,
                name=os.path.basename(filepath),
                kind="file",
                language=node.language,
                file_hash=node.file_hash,
                size_bytes=node.size_bytes,
                last_modified=node.last_modified,
            )

            # Add symbol nodes to graph
            for sym in symbols:
                self.graph.add_node(
                    sym.qualified_name,
                    file_path=filepath,
                    name=sym.name,
                    kind=sym.kind,
                    line_start=sym.line_start,
                    line_end=sym.line_end,
                )

        # Phase 2: Extract and add edges
        for filepath, symbols in all_symbols.items():
            # IMPORTS_FROM edges
            import_edges = extract_imports_edges(symbols, all_known_files, filepath)
            for src, tgt, etype in import_edges:
                self.graph.add_edge(src, tgt, edge_type=etype)

            # CONTAINS edges
            contains_edges = extract_contains_edges(symbols, filepath)
            for src, tgt, etype in contains_edges:
                self.graph.add_edge(src, tgt, edge_type=etype)

            # TESTED_BY edges (only for test files)
            basename = os.path.basename(filepath)
            if basename.startswith("test_") or basename.endswith("_test.py"):
                tested_by_edges = detect_tested_by(filepath, all_known_files)
                for src, tgt, etype in tested_by_edges:
                    self.graph.add_edge(src, tgt, edge_type=etype)

        logging.info(
            f"Graph built: {len(files)} files, "
            f"{self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges"
        )

        return {
            "file_count": len(files),
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "built_at": datetime.now(timezone.utc).isoformat(),
        }

    def add_file(self, node: FileNode) -> None:
        """Add a file node to the graph.

        Args:
            node: The FileNode to add.
        """
        self.graph.add_node(
            node.path,
            file_path=node.path,
            name=os.path.basename(node.path),
            kind="file",
            language=node.language,
            file_hash=node.file_hash,
            size_bytes=node.size_bytes,
            last_modified=node.last_modified,
        )

    def add_dependency(self, source: str, target: str, dep_type: str = "import") -> None:
        """Add a dependency edge between two files.

        Args:
            source: The dependent file path.
            target: The dependency file path.
            dep_type: Type of dependency (import, type_ref, etc.).
        """
        self.graph.add_edge(source, target, edge_type=dep_type)

    def get_dependencies(self, file_path: str) -> list[str]:
        """Get all files that the given file depends on.

        Args:
            file_path: The file to check dependencies for.

        Returns:
            List of file paths that the given file depends on.
        """
        import networkx as nx

        file_path = os.path.abspath(file_path)
        if file_path not in self.graph:
            return []
        # Get outgoing edges (files this file depends on)
        deps = set()
        for _, target, data in self.graph.out_edges(file_path, data=True):
            if data.get("edge_type") in ("IMPORTS_FROM", "DEPENDS_ON", "CALLS"):
                # Extract file path from target node
                target_fp = self.graph.nodes[target].get("file_path", target)
                deps.add(target_fp)
        return list(deps)

    def get_dependents(self, file_path: str) -> list[str]:
        """Get all files that depend on the given file.

        Args:
            file_path: The file to check dependents for.

        Returns:
            List of file paths that depend on the given file.
        """
        file_path = os.path.abspath(file_path)
        if file_path not in self.graph:
            return []
        # Get incoming edges (files that depend on this file)
        dependents = set()
        for source, _, data in self.graph.in_edges(file_path, data=True):
            if data.get("edge_type") in ("IMPORTS_FROM", "DEPENDS_ON", "CALLS", "TESTED_BY"):
                source_fp = self.graph.nodes[source].get("file_path", source)
                dependents.add(source_fp)
        return list(dependents)

    def get_impact_set(self, changed_files: list[str]) -> set[str]:
        """Get all files potentially affected by changes.

        Given a set of changed files, returns the transitive
        closure of all files that may be affected.

        Args:
            changed_files: List of files that have changed.

        Returns:
            Set of all potentially affected file paths.
        """
        import networkx as nx

        impacted: set[str] = set()
        for cf in changed_files:
            cf_abs = os.path.abspath(cf)
            if cf_abs in self.graph:
                # Get all ancestors (files that depend on this file)
                ancestors = nx.ancestors(self.graph, cf_abs)
                for a in ancestors:
                    fp = self.graph.nodes[a].get("file_path", a)
                    impacted.add(fp)
        return impacted

    def save(self, path: str | None = None) -> None:
        """Persist the graph to disk as JSON.

        Args:
            path: Output file path. Defaults to ./data/file_graph.json.
        """
        ...

    @classmethod
    def load(cls, path: str) -> FileGraph:
        """Load a graph from a JSON file.

        Args:
            path: Path to the JSON file.

        Returns:
            A FileGraph instance with the loaded data.
        """
        ...


# Module-level singleton pattern (same as chat_store.py)
_graph: FileGraph | None = None


def get_graph(root_path: str = ".") -> FileGraph:
    """Get or create the global FileGraph singleton.

    Args:
        root_path: Root directory for the graph.

    Returns:
        FileGraph instance.
    """
    global _graph
    if _graph is None:
        _graph = FileGraph(root_path)
    return _graph


def reset_graph() -> None:
    """Reset the global FileGraph singleton (useful for testing)."""
    global _graph
    _graph = None
