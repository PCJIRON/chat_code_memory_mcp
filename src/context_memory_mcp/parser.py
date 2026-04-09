"""Tree-sitter AST parser for multi-language source code analysis.

Uses tree-sitter-language-pack to parse various programming languages
and extract structural information (imports, classes, functions, etc.).
"""

from __future__ import annotations

from typing import Any


class ParsedSymbol:
    """Represents a symbol extracted from source code.

    Attributes:
        name: Symbol name (function, class, variable).
        kind: Symbol type ("function", "class", "import", etc.).
        file_path: Source file containing the symbol.
        line_start: Starting line number (1-based).
        line_end: Ending line number (1-based).
        docstring: Extracted docstring if available.
    """

    def __init__(
        self,
        name: str,
        kind: str,
        file_path: str,
        line_start: int,
        line_end: int,
        docstring: str | None = None,
    ) -> None:
        """Initialize a ParsedSymbol.

        Args:
            name: Symbol name.
            kind: Symbol type.
            file_path: Source file path.
            line_start: Starting line number.
            line_end: Ending line number.
            docstring: Extracted docstring.
        """
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serialize the symbol to a dictionary.

        Returns:
            Dictionary representation for JSON serialization.
        """
        ...


class ASTParser:
    """Multi-language AST parser using tree-sitter.

    Parses source code files and extracts structural information
    including imports, classes, functions, and type annotations.

    Attributes:
        language_pack: The tree-sitter language pack in use.
    """

    def __init__(self, language: str = "auto") -> None:
        """Initialize the ASTParser.

        Args:
            language: Default language hint. "auto" detects from file extension.
        """
        ...

    def parse_file(self, file_path: str) -> list[ParsedSymbol]:
        """Parse a source file and extract all symbols.

        Args:
            file_path: Path to the source file.

        Returns:
            List of ParsedSymbol objects found in the file.
        """
        ...

    def parse_content(self, content: str, language: str) -> list[ParsedSymbol]:
        """Parse source code content directly.

        Args:
            content: Source code text.
            language: Programming language identifier.

        Returns:
            List of ParsedSymbol objects found in the content.
        """
        ...

    def get_imports(self, file_path: str) -> list[str]:
        """Extract import statements from a source file.

        Args:
            file_path: Path to the source file.

        Returns:
            List of imported module/file paths.
        """
        ...

    def detect_language(self, file_path: str) -> str:
        """Detect the programming language of a file.

        Args:
            file_path: Path to the source file.

        Returns:
            Language identifier string (e.g., "python", "typescript").
        """
        ...
