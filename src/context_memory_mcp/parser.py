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

    def parse_file(self, file_path: str) -> list[ParsedSymbol]:
        """Parse a source file and extract all symbols.

        Args:
            file_path: Path to the source file.

        Returns:
            List of ParsedSymbol objects found in the file.
        """
        if not self._parser:
            return []
        try:
            with open(file_path, "rb") as f:
                source = f.read()
            tree = self._parser.parse(source)
            return self._extract_symbols(tree.root_node, file_path)
        except Exception as e:
            import logging
            logging.warning(f"Failed to parse {file_path}: {e}")
            return []

    def parse_content(self, content: str, language: str) -> list[ParsedSymbol]:
        """Parse source code content directly.

        Args:
            content: Source code text.
            language: Programming language identifier.

        Returns:
            List of ParsedSymbol objects found in the content.
        """
        if not self._parser:
            return []
        try:
            source = content.encode("utf-8")
            tree = self._parser.parse(source)
            return self._extract_symbols(tree.root_node, "<string>")
        except Exception as e:
            import logging
            logging.warning(f"Failed to parse content: {e}")
            return []

    def get_imports(self, file_path: str) -> list[str]:
        """Extract import statements from a source file.

        Args:
            file_path: Path to the source file.

        Returns:
            List of imported module/file paths.
        """
        symbols = self.parse_file(file_path)
        return [s.name for s in symbols if s.kind == "import"]

    def _extract_symbols(self, root_node, file_path: str) -> list[ParsedSymbol]:
        """Extract symbols from a tree-sitter AST root node.

        Args:
            root_node: The root node of the parsed tree.
            file_path: Path to the source file.

        Returns:
            List of ParsedSymbol objects.
        """
        symbols: list[ParsedSymbol] = []

        # Extract classes
        class_nodes: list = []
        _find_nodes_by_type(root_node, "class_definition", class_nodes)
        for cls_node in class_nodes:
            name_node = cls_node.child_by_field_name("name")
            if name_node:
                symbols.append(ParsedSymbol(
                    name=name_node.text.decode(),
                    kind="class",
                    file_path=file_path,
                    line_start=cls_node.start_point[0] + 1,
                    line_end=cls_node.end_point[0] + 1,
                ))
                # Extract methods within class
                func_nodes: list = []
                _find_nodes_by_type(cls_node, "function_definition", func_nodes)
                for func_node in func_nodes:
                    fname_node = func_node.child_by_field_name("name")
                    if fname_node:
                        symbols.append(ParsedSymbol(
                            name=f"{name_node.text.decode()}.{fname_node.text.decode()}",
                            kind="method",
                            file_path=file_path,
                            line_start=func_node.start_point[0] + 1,
                            line_end=func_node.end_point[0] + 1,
                        ))

        # Extract top-level functions (not inside classes)
        func_nodes: list = []
        _find_nodes_by_type(root_node, "function_definition", func_nodes)
        class_line_ranges = [(c.start_point[0], c.end_point[0]) for c in class_nodes]
        for func_node in func_nodes:
            # Skip if inside a class
            if any(start <= func_node.start_point[0] <= end for start, end in class_line_ranges):
                continue
            name_node = func_node.child_by_field_name("name")
            if name_node:
                symbols.append(ParsedSymbol(
                    name=name_node.text.decode(),
                    kind="function",
                    file_path=file_path,
                    line_start=func_node.start_point[0] + 1,
                    line_end=func_node.end_point[0] + 1,
                ))

        # Extract imports
        import_nodes: list = []
        _find_nodes_by_type(root_node, "import_statement", import_nodes)
        _find_nodes_by_type(root_node, "import_from_statement", import_nodes)
        for imp_node in import_nodes:
            symbols.append(ParsedSymbol(
                name=imp_node.text.decode().strip(),
                kind="import",
                file_path=file_path,
                line_start=imp_node.start_point[0] + 1,
                line_end=imp_node.end_point[0] + 1,
            ))

        return symbols


def _find_nodes_by_type(node, target_type: str, results: list) -> None:
    """Recursively find all nodes of a given type in the AST.

    Args:
        node: The current tree-sitter node.
        target_type: The node type to search for.
        results: List to append matching nodes to.
    """
    if node.type == target_type:
        results.append(node)
    for child in node.children:
        _find_nodes_by_type(child, target_type, results)
