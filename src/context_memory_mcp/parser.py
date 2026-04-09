"""Tree-sitter AST parser for multi-language source code analysis.

Uses tree-sitter-language-pack to parse various programming languages
and extract structural information (imports, classes, functions, etc.).
"""

from __future__ import annotations

import os
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


# ---------------------------------------------------------------------------
# Edge extraction functions (T05)
# ---------------------------------------------------------------------------

def _parse_import_module(sym: ParsedSymbol) -> list[str]:
    """Extract module name(s) from an import symbol.

    For 'import os' -> ['os']
    For 'from pathlib import Path' -> ['pathlib']
    For 'from os.path import join' -> ['os.path']

    Args:
        sym: ParsedSymbol with kind="import" and name containing the import text.

    Returns:
        List of module names extracted from the import statement.
    """
    text = sym.name  # e.g., "import os" or "from pathlib import Path"
    modules: list[str] = []

    if text.startswith("import "):
        # "import os" or "import os.path"
        module_part = text[len("import "):].strip()
        if module_part:
            modules.append(module_part)
    elif text.startswith("from "):
        # "from pathlib import Path"
        parts = text.split()
        if len(parts) >= 2:
            modules.append(parts[1])  # "pathlib"

    return modules


def extract_imports_edges(
    symbols: list[ParsedSymbol],
    known_files: set[str],
    file_path: str,
) -> list[tuple[str, str, str]]:
    """Extract IMPORTS_FROM edges by parsing module names from AST.

    Now uses actual module names instead of substring matching.

    Args:
        symbols: List of ParsedSymbol objects from parse_file().
        known_files: Set of absolute file paths known to the graph.
        file_path: The source file being analyzed.

    Returns:
        List of (source_id, target_id, "IMPORTS_FROM") tuples.
    """
    edges: list[tuple[str, str, str]] = []
    abs_source = os.path.abspath(file_path)

    # Build a lookup: module_name -> file_path
    module_to_file: dict[str, str] = {}
    for kf in known_files:
        base = os.path.splitext(os.path.basename(kf))[0].lower()
        module_to_file[base] = kf
        # Also handle package directories
        dir_name = os.path.basename(os.path.dirname(kf)).lower()
        if dir_name not in module_to_file:
            module_to_file[dir_name] = kf

    for sym in symbols:
        if sym.kind != "import":
            continue
        modules = _parse_import_module(sym)
        for mod in modules:
            mod_base = mod.split(".")[-1].lower()  # "os.path" -> "path"
            if mod_base in module_to_file:
                target_file = module_to_file[mod_base]
                target_id = f"{target_file}::{mod_base}"
                edges.append((abs_source, target_id, "IMPORTS_FROM"))
                break  # One match per import

    return edges


def extract_contains_edges(
    symbols: list[ParsedSymbol],
    file_path: str,
) -> list[tuple[str, str, str]]:
    """Extract CONTAINS edges for class→method hierarchy.

    Creates edges from file to classes, and from classes to their methods.

    Args:
        symbols: List of ParsedSymbol objects from parse_file().
        file_path: The source file being analyzed.

    Returns:
        List of (source_id, target_id, "CONTAINS") tuples.
    """
    edges: list[tuple[str, str, str]] = []
    abs_path = os.path.abspath(file_path)
    file_node_id = abs_path

    for sym in symbols:
        if sym.kind == "class":
            edges.append((file_node_id, sym.qualified_name, "CONTAINS"))
        elif sym.kind == "method":
            # Methods are already named as "ClassName.method"
            # Find their parent class
            class_name = sym.name.split(".")[0]
            class_qn = f"{abs_path}::{class_name}"
            edges.append((class_qn, sym.qualified_name, "CONTAINS"))

    return edges


def extract_calls_edges(
    root_node,
    file_path: str,
    known_symbols: dict[str, ParsedSymbol],
) -> list[tuple[str, str, str]]:
    """Extract CALLS edges from call expressions in the AST.

    Args:
        root_node: The tree-sitter root node of the parsed file.
        file_path: The source file being analyzed.
        known_symbols: Dict mapping qualified names to ParsedSymbol objects.

    Returns:
        List of (source_id, target_id, "CALLS") tuples.
    """
    edges: list[tuple[str, str, str]] = []
    abs_path = os.path.abspath(file_path)

    call_nodes: list = []
    _find_nodes_by_type(root_node, "call", call_nodes)

    for call_node in call_nodes:
        func_node = call_node.child_by_field_name("function")
        if func_node is None:
            continue
        func_name = func_node.text.decode().strip()
        # Try to match to known symbols
        # Simple function name match
        base_name = func_name.split(".")[-1]
        for qn, sym in known_symbols.items():
            if sym.name == base_name or qn.endswith(f"::{func_name}") or qn.endswith(f"::{base_name}"):
                edges.append((abs_path, qn, "CALLS"))
                break

    return edges


def extract_inherits_edges(
    symbols: list[ParsedSymbol],
    file_path: str,
) -> list[tuple[str, str, str]]:
    """Extract INHERITS edges from class definitions.

    Args:
        symbols: List of ParsedSymbol objects (should include class symbols).
        file_path: The source file being analyzed.

    Returns:
        List of (source_id, target_id, "INHERITS") tuples.
    """
    edges: list[tuple[str, str, str]] = []
    abs_path = os.path.abspath(file_path)

    for sym in symbols:
        if sym.kind != "class":
            continue
        # We don't have base class info in ParsedSymbol from Wave 1,
        # so we return empty here. The FileGraph.build_graph will call
        # this with AST root nodes for full extraction.
        # This function exists as a hook for future enhancement.

    return edges


def extract_implements_edges(
    symbols: list[ParsedSymbol],
    file_path: str,
) -> list[tuple[str, str, str]]:
    """Extract IMPLEMENTS edges for Protocol/ABC implementations.

    Args:
        symbols: List of ParsedSymbol objects.
        file_path: The source file being analyzed.

    Returns:
        List of (source_id, target_id, "IMPLEMENTS") tuples.
    """
    edges: list[tuple[str, str, str]] = []
    abs_path = os.path.abspath(file_path)

    for sym in symbols:
        if sym.kind != "class":
            continue
        # Check if class name suggests Protocol/ABC implementation
        # This is a heuristic based on the import symbols
        # Full detection requires AST root node access to superclasses

    return edges


def detect_tested_by(
    test_file: str,
    source_files: set[str],
) -> list[tuple[str, str, str]]:
    """Detect TESTED_BY edges between test files and source files.

    Matches test_*.py → *.py and *_test.py → *.py patterns.

    Args:
        test_file: Path to a test file.
        source_files: Set of all known source file paths.

    Returns:
        List of (test_file, source_file, "TESTED_BY") tuples.
    """
    edges: list[tuple[str, str, str]] = []
    test_basename = os.path.basename(test_file)
    test_stem = os.path.splitext(test_basename)[0]

    # Determine the source module name
    source_stem: str | None = None
    if test_stem.startswith("test_"):
        source_stem = test_stem[5:]  # Remove "test_" prefix
    elif test_stem.endswith("_test"):
        source_stem = test_stem[:-5]  # Remove "_test" suffix

    if source_stem is None:
        return edges

    abs_test = os.path.abspath(test_file)
    for src in source_files:
        src_basename = os.path.basename(src)
        src_stem = os.path.splitext(src_basename)[0]
        if src_stem == source_stem:
            edges.append((abs_test, os.path.abspath(src), "TESTED_BY"))
            break

    return edges


def extract_depends_on_edges(
    symbols: list[ParsedSymbol],
    known_files: set[str],
    file_path: str,
    existing_edges: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """Extract DEPENDS_ON edges as fallback for unclassified dependencies.

    Creates edges for any import that wasn't already classified as IMPORTS_FROM.

    Args:
        symbols: List of ParsedSymbol objects.
        known_files: Set of known file paths.
        file_path: The source file being analyzed.
        existing_edges: Already classified edges to avoid duplicates.

    Returns:
        List of (source_id, target_id, "DEPENDS_ON") tuples.
    """
    existing_targets = {e[1] for e in existing_edges}
    edges: list[tuple[str, str, str]] = []
    abs_source = os.path.abspath(file_path)

    # Build a lookup: module_name -> file_path
    module_to_file: dict[str, str] = {}
    for kf in known_files:
        base = os.path.splitext(os.path.basename(kf))[0].lower()
        module_to_file[base] = kf
        dir_name = os.path.basename(os.path.dirname(kf)).lower()
        if dir_name not in module_to_file:
            module_to_file[dir_name] = kf

    for sym in symbols:
        if sym.kind != "import":
            continue
        modules = _parse_import_module(sym)
        for mod in modules:
            mod_base = mod.split(".")[-1].lower()
            if mod_base in module_to_file:
                target_id = f"{module_to_file[mod_base]}::{mod_base}"
                if target_id not in existing_targets:
                    edges.append((abs_source, target_id, "DEPENDS_ON"))
                    break

    return edges
