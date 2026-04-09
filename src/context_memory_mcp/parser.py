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
            line_start: Starting line number (1-based).
            line_end: Ending line number (1-based).
            docstring: Extracted docstring.
        """
        self.name = name
        self.kind = kind
        self.file_path = file_path
        self.line_start = line_start
        self.line_end = line_end
        self.docstring = docstring

    @property
    def qualified_name(self) -> str:
        """Return the fully qualified symbol name.

        Returns:
            String in format "/abs/path/file.py::symbol_name".
        """
        import os
        abs_path = os.path.abspath(self.file_path)
        return f"{abs_path}::{self.name}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the symbol to a dictionary.

        Returns:
            Dictionary representation for JSON serialization.
        """
        return {
            "name": self.name,
            "kind": self.kind,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "docstring": self.docstring,
            "qualified_name": self.qualified_name,
        }


class ASTParser:
    """Multi-language AST parser using tree-sitter.

    Parses source code files and extracts structural information
    including imports, classes, functions, and type annotations.

    Attributes:
        language_pack: The tree-sitter language pack in use.
    """

    # Mapping from file extensions to language identifiers
    _EXTENSION_MAP = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
    }

    def __init__(self, language: str = "auto") -> None:
        """Initialize the ASTParser.

        Args:
            language: Default language hint. "auto" detects from file extension.
        """
        self.language_hint = language
        self._parser = None
        self._language = None
        self._init_parser()

    def _init_parser(self) -> None:
        """Initialize tree-sitter parser using get_binding (works without network).

        Uses the confirmed working pattern:
            tslp.get_binding("python") -> ts.Language(binding) -> ts.Parser(lang)
        """
        try:
            import tree_sitter as ts
            import tree_sitter_language_pack as tslp
        except ImportError as e:
            import logging
            logging.warning(f"Failed to import tree-sitter packages: {e}")
            self._parser = None
            return

        try:
            binding = tslp.get_binding("python")
            lang = ts.Language(binding)
            self._parser = ts.Parser(lang)
        except Exception as e:
            import logging
            logging.warning(f"Failed to initialize tree-sitter parser: {e}")
            self._parser = None

    def detect_language(self, file_path: str) -> str:
        """Detect the programming language of a file.

        Uses file extension lookup as primary method since
        detect_language_from_path requires content-based detection
        which may be unreliable. Falls back to extension mapping.

        Args:
            file_path: Path to the source file.

        Returns:
            Language identifier string (e.g., "python", "typescript"),
            or "unsupported" if the language cannot be determined.
        """
        try:
            import tree_sitter_language_pack as tslp
            # Try content-based detection first
            detected = tslp.detect_language_from_path(file_path)
            if detected:
                return detected
        except Exception:
            pass

        # Fallback to extension-based detection
        import os
        _, ext = os.path.splitext(file_path)
        return self._EXTENSION_MAP.get(ext.lower(), "unsupported")
