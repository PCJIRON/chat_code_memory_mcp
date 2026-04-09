"""File relationship graph tracking.

Uses NetworkX to track dependencies, imports, and relationships
between files in a codebase for context-aware retrieval.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import Field

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

    def get_file_nodes(self, file_path: str) -> list[str]:
        """Return all node IDs belonging to a file.

        Includes the file-level node and all symbol nodes within the file.

        Args:
            file_path: Path to the file to query.

        Returns:
            List of node IDs (file path and symbol qualified names).
        """
        file_path = os.path.abspath(file_path)
        return [
            n for n in self.graph.nodes()
            if self.graph.nodes[n].get("file_path") == file_path
        ]

    def get_subgraph(self, file_path: str) -> dict:
        """Return structured dict for MCP response.

        Args:
            file_path: Path to the file to query.

        Returns:
            Dictionary with file, nodes, edges, dependencies, dependents,
            and impact_summary suitable for JSON serialization.
        """
        file_path = os.path.abspath(file_path)
        nodes = self.get_file_nodes(file_path)
        node_set = set(nodes)
        edges = [
            (s, t, self.graph[s][t])
            for s, t in self.graph.edges()
            if s in node_set or t in node_set
        ]
        deps = self.get_dependencies(file_path)
        dependents = self.get_dependents(file_path)
        return {
            "file": file_path,
            "nodes": [self.graph.nodes[n] for n in nodes],
            "edges": [
                {"source": s, "target": t, **attr}
                for s, t, attr in edges
            ],
            "dependencies": deps,
            "dependents": dependents,
            "impact_summary": {
                "direct_dependencies": len(deps),
                "direct_dependents": len(dependents),
            },
        }

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

        Serializes the NetworkX graph using node_link_data format
        along with the SHA-256 hash index and metadata.

        Args:
            path: Output file path. Defaults to ./data/file_graph.json.
        """
        import networkx as nx

        if path is None:
            path = os.path.join(self.root_path, "data", "file_graph.json")

        # Ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # Serialize graph using node_link_data (NO attrs param in NetworkX 3.x)
        data = nx.node_link_data(self.graph)
        # Add hash index
        data["_hash_index"] = self._hash_index
        data["_metadata"] = {
            "root_path": self.root_path,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> FileGraph:
        """Load a graph from a JSON file.

        Reconstructs the NetworkX DiGraph from node_link_data format
        and restores the SHA-256 hash index.

        Args:
            path: Path to the JSON file.

        Returns:
            A FileGraph instance with the loaded data.
        """
        import networkx as nx

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Reconstruct graph
        graph_data = {k: v for k, v in data.items() if k not in ("_hash_index", "_metadata")}
        G = nx.node_link_graph(graph_data)

        fg = cls(root_path=data.get("_metadata", {}).get("root_path", "."))
        fg.graph = G
        fg._hash_index = data.get("_hash_index", {})
        return fg

    def has_changed(self, file_path: str) -> bool:
        """Check if a file has changed since last indexed.

        Compares current SHA-256 hash against stored hash in _hash_index.

        Args:
            file_path: Path to the file to check.

        Returns:
            True if file content differs from stored hash, False otherwise.
        """
        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path):
            return True  # Removed files are considered "changed"
        current_hash = FileNode.compute_hash(file_path)
        stored = self._hash_index.get(file_path, {})
        return current_hash != stored.get("hash")

    def update_graph(self, directory: str, changed_files: list[str] | None = None) -> dict:
        """Incrementally update the graph with changed files.

        If changed_files is None, auto-detects changes by comparing
        SHA-256 hashes against the stored index.

        Args:
            directory: Root directory to scan for changes.
            changed_files: Optional explicit list of changed file paths.

        Returns:
            Summary dict with added, removed, updated, unchanged, total_files.
        """
        import logging
        from datetime import datetime, timezone
        from context_memory_mcp.parser import (
            extract_imports_edges,
            extract_contains_edges,
            detect_tested_by,
        )

        directory = os.path.abspath(directory)
        all_files = list(self._walk_code_files(directory))
        all_known_files = set(all_files)

        if changed_files is None:
            # Auto-detect changes
            changed_files = [f for f in all_files if self.has_changed(f)]
            # Detect removed files
            removed_files = [f for f in self._hash_index if f not in all_files]
        else:
            changed_files = [os.path.abspath(f) for f in changed_files]
            removed_files = [f for f in self._hash_index if f not in all_files]

        logging.info(
            f"Updating graph: {len(changed_files)} changed, {len(removed_files)} removed"
        )

        # Remove changed/removed nodes from graph
        files_to_remove = set(changed_files) | set(removed_files)
        for f in files_to_remove:
            nodes_to_remove = [
                n for n in self.graph.nodes()
                if self.graph.nodes[n].get("file_path") == f
            ]
            self.graph.remove_nodes_from(nodes_to_remove)
            if f in self._hash_index:
                del self._hash_index[f]

        # Re-parse changed files that still exist
        updated_count = 0
        new_symbols: dict[str, list] = {}  # file_path -> symbols (retain for edge extraction)
        for f in changed_files:
            if not os.path.exists(f):
                continue
            symbols = self._parser.parse_file(f)
            new_symbols[f] = symbols

            # Create FileNode and update from disk
            node = FileNode(path=f)
            node.update_from_file(f)
            node.language = self._parser.detect_language(f)

            # Store in hash index
            self._hash_index[f] = {
                "hash": node.file_hash,
                "language": node.language,
                "size_bytes": node.size_bytes,
                "last_modified": node.last_modified,
            }

            # Add file-level node to graph
            self.graph.add_node(
                f,
                file_path=f,
                name=os.path.basename(f),
                kind="file",
                language=node.language,
                file_hash=node.file_hash,
                size_bytes=node.size_bytes,
                last_modified=node.last_modified,
            )

            # Add symbol nodes
            for sym in symbols:
                self.graph.add_node(
                    sym.qualified_name,
                    file_path=f,
                    name=sym.name,
                    kind=sym.kind,
                    line_start=sym.line_start,
                    line_end=sym.line_end,
                )

            updated_count += 1

        # Re-extract edges for changed files using retained symbols (NO re-parsing)
        for f in changed_files:
            if not os.path.exists(f):
                continue
            symbols = new_symbols.get(f)
            if symbols is None:
                # Fallback: only re-parse if symbols weren't retained (shouldn't happen)
                symbols = self._parser.parse_file(f)

            # IMPORTS_FROM edges
            import_edges = extract_imports_edges(symbols, all_known_files, f)
            for src, tgt, etype in import_edges:
                self.graph.add_edge(src, tgt, edge_type=etype)

            # CONTAINS edges
            contains_edges_list = extract_contains_edges(symbols, f)
            for src, tgt, etype in contains_edges_list:
                self.graph.add_edge(src, tgt, edge_type=etype)

            # TESTED_BY edges
            basename = os.path.basename(f)
            if basename.startswith("test_") or basename.endswith("_test.py"):
                tested_by_edges = detect_tested_by(f, all_known_files)
                for src, tgt, etype in tested_by_edges:
                    self.graph.add_edge(src, tgt, edge_type=etype)

        removed_count = len(removed_files)
        unchanged_count = len(all_files) - len(changed_files)

        logging.info(
            f"Graph updated: {updated_count} updated, {removed_count} removed, "
            f"{unchanged_count} unchanged"
        )

        return {
            "added": updated_count,
            "removed": removed_count,
            "updated": updated_count,
            "unchanged": unchanged_count,
            "total_files": len(all_files),
        }


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


def register(mcp) -> None:
    """Register file graph tools with the MCP server.

    Registers track_files and get_file_graph MCP tools.

    Args:
        mcp: FastMCP server instance.
    """

    @mcp.tool(
        name="track_files",
        description="Build or update the file relationship graph for a directory",
    )
    async def track_files(
        directory: Annotated[str, Field(description="Path to the directory to scan")],
    ) -> str:
        """Build or update file graph. Returns JSON summary.

        Args:
            directory: Path to the directory to scan.

        Returns:
            JSON string with status, file_count, node_count, edge_count.
        """
        graph = get_graph()
        result = graph.build_graph(directory)
        return json.dumps({"status": "ok", **result}, indent=2)

    @mcp.tool(
        name="get_file_graph",
        description="Get the file relationship subgraph for a specific file",
    )
    async def get_file_graph_tool(
        file_path: Annotated[str, Field(description="Path to the file to query")],
    ) -> str:
        """Get file subgraph. Returns JSON with nodes, edges, dependencies.

        Args:
            file_path: Path to the file to query.

        Returns:
            JSON string with subgraph data or error message.
        """
        graph = get_graph()
        # Load from disk if graph is empty
        if graph.graph.number_of_nodes() == 0:
            try:
                default_path = os.path.join(graph.root_path, "data", "file_graph.json")
                graph = FileGraph.load(default_path)
            except (FileNotFoundError, OSError):
                return json.dumps(
                    {"error": "No graph data available. Run track_files first."},
                    indent=2,
                )
        result = graph.get_subgraph(file_path)
        return json.dumps(result, indent=2)
