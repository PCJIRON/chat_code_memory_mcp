"""File relationship graph tracking.

Uses NetworkX to track dependencies, imports, and relationships
between files in a codebase for context-aware retrieval.
"""

from __future__ import annotations

from typing import Any


class FileNode:
    """Represents a single file in the relationship graph.

    Attributes:
        path: Absolute or relative file path.
        language: Detected programming language.
        size_bytes: File size in bytes.
        last_modified: ISO 8601 timestamp of last modification.
        hash: Content hash for change detection.
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
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serialize the node to a dictionary.

        Returns:
            Dictionary representation for JSON serialization.
        """
        ...


class FileGraph:
    """Graph of file relationships in a codebase.

    Tracks imports, type references, and structural dependencies
    between files using a NetworkX directed graph.

    Attributes:
        root_path: Root directory of the tracked codebase.
        graph: The underlying NetworkX DiGraph.
    """

    def __init__(self, root_path: str = ".") -> None:
        """Initialize the FileGraph.

        Args:
            root_path: Root directory of the codebase to track.
        """
        ...

    def add_file(self, node: FileNode) -> None:
        """Add a file node to the graph.

        Args:
            node: The FileNode to add.
        """
        ...

    def add_dependency(self, source: str, target: str, dep_type: str = "import") -> None:
        """Add a dependency edge between two files.

        Args:
            source: The dependent file path.
            target: The dependency file path.
            dep_type: Type of dependency (import, type_ref, etc.).
        """
        ...

    def get_dependencies(self, file_path: str) -> list[str]:
        """Get all files that the given file depends on.

        Args:
            file_path: The file to check dependencies for.

        Returns:
            List of file paths that the given file depends on.
        """
        ...

    def get_dependents(self, file_path: str) -> list[str]:
        """Get all files that depend on the given file.

        Args:
            file_path: The file to check dependents for.

        Returns:
            List of file paths that depend on the given file.
        """
        ...

    def get_impact_set(self, changed_files: list[str]) -> set[str]:
        """Get all files potentially affected by changes.

        Given a set of changed files, returns the transitive
        closure of all files that may be affected.

        Args:
            changed_files: List of files that have changed.

        Returns:
            Set of all potentially affected file paths.
        """
        ...

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
