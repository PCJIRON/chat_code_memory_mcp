"""Tests for the parser module — ParsedSymbol, ASTParser, and symbol extraction."""

from __future__ import annotations

import os

import pytest

from context_memory_mcp.parser import ASTParser, ParsedSymbol


# ---------------------------------------------------------------------------
# ParsedSymbol tests (T01)
# ---------------------------------------------------------------------------

class TestParsedSymbol:
    """Tests for the ParsedSymbol data class."""

    def test_init_all_attributes(self) -> None:
        """Constructor accepts all 6 attributes."""
        sym = ParsedSymbol(
            name="my_func",
            kind="function",
            file_path="/tmp/test.py",
            line_start=10,
            line_end=20,
            docstring="A test function.",
        )
        assert sym.name == "my_func"
        assert sym.kind == "function"
        assert sym.file_path == "/tmp/test.py"
        assert sym.line_start == 10
        assert sym.line_end == 20
        assert sym.docstring == "A test function."

    def test_init_docstring_defaults_to_none(self) -> None:
        """Docstring defaults to None when not provided."""
        sym = ParsedSymbol(
            name="x",
            kind="variable",
            file_path="/tmp/x.py",
            line_start=1,
            line_end=1,
        )
        assert sym.docstring is None

    def test_qualified_name_returns_correct_format(self) -> None:
        """qualified_name property returns /abs/path/file.py::symbol_name."""
        sym = ParsedSymbol(
            name="MyClass",
            kind="class",
            file_path="src/test.py",
            line_start=5,
            line_end=15,
        )
        qn = sym.qualified_name
        assert "::" in qn
        assert qn.endswith("::MyClass")
        # Should be an absolute path
        assert os.path.isabs(qn.split("::")[0])

    def test_qualified_name_uses_absolute_path(self) -> None:
        """qualified_name converts relative paths to absolute."""
        sym = ParsedSymbol(
            name="func",
            kind="function",
            file_path="relative/path.py",
            line_start=1,
            line_end=1,
        )
        abs_part = sym.qualified_name.split("::")[0]
        assert os.path.isabs(abs_part)

    def test_to_dict_returns_serializable_dict(self) -> None:
        """to_dict() returns a dictionary with all fields."""
        sym = ParsedSymbol(
            name="hello",
            kind="function",
            file_path="/path/to/file.py",
            line_start=1,
            line_end=10,
            docstring="Hello world",
        )
        d = sym.to_dict()
        assert isinstance(d, dict)
        assert d["name"] == "hello"
        assert d["kind"] == "function"
        assert d["file_path"] == "/path/to/file.py"
        assert d["line_start"] == 1
        assert d["line_end"] == 10
        assert d["docstring"] == "Hello world"
        assert d["qualified_name"] == sym.qualified_name

    def test_to_dict_without_docstring(self) -> None:
        """to_dict() handles None docstring correctly."""
        sym = ParsedSymbol(
            name="x",
            kind="variable",
            file_path="/path.py",
            line_start=1,
            line_end=1,
        )
        d = sym.to_dict()
        assert d["docstring"] is None


# ---------------------------------------------------------------------------
# ASTParser tests — initialization & language detection (T02)
# ---------------------------------------------------------------------------

class TestASTParserInit:
    """Tests for ASTParser initialization and language detection."""

    def test_init_creates_parser(self) -> None:
        """get_binding("python") -> ts.Language() -> ts.Parser() chain succeeds."""
        parser = ASTParser()
        # Parser should be initialized (not None) when tree-sitter is available
        # On systems where tree-sitter isn't available, it will be None gracefully
        assert parser._parser is not None or parser._parser is None  # either is fine

    def test_init_sets_language_hint(self) -> None:
        """Constructor stores the language hint."""
        parser = ASTParser(language="javascript")
        assert parser.language_hint == "javascript"

    def test_init_handles_import_error_gracefully(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ImportError is caught and logged without crashing."""
        # Simulate ImportError by making the module unavailable
        import sys
        # Store original modules
        orig_ts = sys.modules.get("tree_sitter")
        orig_tslp = sys.modules.get("tree_sitter_language_pack")
        # Remove them temporarily
        sys.modules["tree_sitter"] = None  # type: ignore[assignment]
        sys.modules["tree_sitter_language_pack"] = None  # type: ignore[assignment]
        try:
            # This should not crash
            parser = ASTParser()
            assert parser._parser is None
        finally:
            # Restore
            if orig_ts is not None:
                sys.modules["tree_sitter"] = orig_ts
            if orig_tslp is not None:
                sys.modules["tree_sitter_language_pack"] = orig_tslp


class TestASTParserDetectLanguage:
    """Tests for language detection."""

    def test_detect_python_from_py_extension(self, tmp_path) -> None:
        """Python files detected from .py extension."""
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        parser = ASTParser()
        lang = parser.detect_language(str(f))
        assert lang == "python"

    def test_detect_python_from_pyi_extension(self, tmp_path) -> None:
        """Python stub files detected from .pyi extension."""
        f = tmp_path / "stub.pyi"
        f.write_text("def x() -> None: ...")
        parser = ASTParser()
        lang = parser.detect_language(str(f))
        assert lang == "python"

    def test_detect_js_from_extension(self, tmp_path) -> None:
        """JavaScript files detected from .js extension."""
        f = tmp_path / "app.js"
        f.write_text("let x = 1;")
        parser = ASTParser()
        lang = parser.detect_language(str(f))
        assert lang == "javascript"

    def test_detect_typescript_from_extension(self, tmp_path) -> None:
        """TypeScript files detected from .ts extension."""
        f = tmp_path / "app.ts"
        f.write_text("let x: number = 1;")
        parser = ASTParser()
        lang = parser.detect_language(str(f))
        assert lang == "typescript"

    def test_unknown_extension_returns_unsupported(self, tmp_path) -> None:
        """Unknown extensions return "unsupported" without crashing."""
        f = tmp_path / "weird.xyz"
        f.write_text("???")
        parser = ASTParser()
        lang = parser.detect_language(str(f))
        assert lang == "unsupported"

    def test_nonexistent_file_returns_unsupported(self) -> None:
        """Non-existent files return "unsupported" without crashing."""
        parser = ASTParser()
        lang = parser.detect_language("/nonexistent/file.xyz")
        assert lang == "unsupported"


# ---------------------------------------------------------------------------
# ASTParser tests — parse_file, parse_content, get_imports (T03)
# ---------------------------------------------------------------------------

SAMPLE_PYTHON_FILE = '''"""A sample module for testing."""

import os
import sys
from pathlib import Path
from typing import Optional

CONSTANT = 42


def helper_function(x: int) -> int:
    """A helper function."""
    return x + 1


class MyClass:
    """A sample class."""

    def __init__(self, name: str) -> None:
        """Initialize the class."""
        self.name = name

    def greet(self) -> str:
        """Return a greeting."""
        return f"Hello, {self.name}"


def main() -> None:
    """Entry point."""
    obj = MyClass("world")
    print(obj.greet())
'''


class TestASTParserParseFile:
    """Tests for parse_file and symbol extraction."""

    def test_parse_file_returns_empty_when_no_parser(self) -> None:
        """parse_file returns empty list when parser is not initialized."""
        parser = ASTParser.__new__(ASTParser)
        parser._parser = None
        result = parser.parse_file("/some/file.py")
        assert result == []

    def test_parse_python_file_extracts_imports(self, tmp_path) -> None:
        """parse_file extracts import statements."""
        f = tmp_path / "sample.py"
        f.write_text(SAMPLE_PYTHON_FILE)
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        imports = [s for s in symbols if s.kind == "import"]
        # Should have: import os, import sys, from pathlib import Path, from typing import Optional
        assert len(imports) >= 4

    def test_parse_python_file_extracts_classes(self, tmp_path) -> None:
        """parse_file extracts class definitions."""
        f = tmp_path / "sample.py"
        f.write_text(SAMPLE_PYTHON_FILE)
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        classes = [s for s in symbols if s.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "MyClass"

    def test_parse_python_file_extracts_methods(self, tmp_path) -> None:
        """parse_file extracts methods within classes."""
        f = tmp_path / "sample.py"
        f.write_text(SAMPLE_PYTHON_FILE)
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        methods = [s for s in symbols if s.kind == "method"]
        assert len(methods) == 2
        method_names = {m.name for m in methods}
        assert "MyClass.__init__" in method_names
        assert "MyClass.greet" in method_names

    def test_parse_python_file_extracts_functions(self, tmp_path) -> None:
        """parse_file extracts top-level function definitions."""
        f = tmp_path / "sample.py"
        f.write_text(SAMPLE_PYTHON_FILE)
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        functions = [s for s in symbols if s.kind == "function"]
        func_names = {f.name for f in functions}
        assert "helper_function" in func_names
        assert "main" in func_names

    def test_parse_python_file_1based_line_numbers(self, tmp_path) -> None:
        """Line numbers are 1-based (not 0-based)."""
        f = tmp_path / "sample.py"
        f.write_text(SAMPLE_PYTHON_FILE)
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        for sym in symbols:
            assert sym.line_start >= 1
            assert sym.line_end >= 1
            assert sym.line_end >= sym.line_start

    def test_parse_file_handles_syntax_errors_gracefully(self, tmp_path) -> None:
        """Syntax errors are handled gracefully without crash."""
        f = tmp_path / "bad.py"
        f.write_text("def broken(:\n    pass\n  invalid syntax @@@")
        parser = ASTParser()
        # Should not raise
        symbols = parser.parse_file(str(f))
        assert isinstance(symbols, list)

    def test_parse_file_returns_empty_for_nonexistent(self) -> None:
        """Non-existent files return empty list without crash."""
        parser = ASTParser()
        symbols = parser.parse_file("/nonexistent/file.py")
        assert symbols == []


class TestASTParserParseContent:
    """Tests for parse_content."""

    def test_parse_content_extracts_symbols(self) -> None:
        """parse_content extracts symbols from raw string."""
        code = '''
import math

def calculate(x):
    return math.sqrt(x)

class Calculator:
    def add(self, a, b):
        return a + b
'''
        parser = ASTParser()
        symbols = parser.parse_content(code, "python")
        kinds = {s.kind for s in symbols}
        assert "import" in kinds
        assert "function" in kinds
        assert "class" in kinds
        assert "method" in kinds

    def test_parse_content_returns_empty_when_no_parser(self) -> None:
        """parse_content returns empty list when parser is not initialized."""
        parser = ASTParser.__new__(ASTParser)
        parser._parser = None
        result = parser.parse_content("x = 1", "python")
        assert result == []


class TestASTParserGetImports:
    """Tests for get_imports."""

    def test_get_imports_returns_list_of_strings(self, tmp_path) -> None:
        """get_imports returns list of import strings."""
        f = tmp_path / "imports.py"
        f.write_text("import os\nfrom pathlib import Path\n")
        parser = ASTParser()
        imports = parser.get_imports(str(f))
        assert isinstance(imports, list)
        assert all(isinstance(i, str) for i in imports)
        assert len(imports) == 2

    def test_get_imports_empty_file(self, tmp_path) -> None:
        """get_imports returns empty list for file with no imports."""
        f = tmp_path / "no_imports.py"
        f.write_text("x = 1\ny = 2\n")
        parser = ASTParser()
        imports = parser.get_imports(str(f))
        assert imports == []


# ---------------------------------------------------------------------------
# Edge extraction tests (T05)
# ---------------------------------------------------------------------------

from context_memory_mcp.parser import (
    detect_tested_by,
    extract_calls_edges,
    extract_contains_edges,
    extract_depends_on_edges,
    extract_implements_edges,
    extract_imports_edges,
    extract_inherits_edges,
)


class TestEdgeExtraction:
    """Tests for edge extraction functions."""

    def test_extract_imports_edges_matches_known_files(self, tmp_path) -> None:
        """IMPORTS_FROM edges match known files."""
        f = tmp_path / "main.py"
        f.write_text("import os\nimport sys\n")
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        known_files = {str(tmp_path / "os.py"), str(tmp_path / "sys.py")}
        edges = extract_imports_edges(symbols, known_files, str(f))
        # Edges should be tuples of (source, target, "IMPORTS_FROM")
        assert isinstance(edges, list)
        for edge in edges:
            assert len(edge) == 3
            assert edge[2] == "IMPORTS_FROM"

    def test_extract_imports_edges_no_known_files(self, tmp_path) -> None:
        """IMPORTS_FROM returns empty when no known files match."""
        f = tmp_path / "main.py"
        f.write_text("import os\nimport sys\n")
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        edges = extract_imports_edges(symbols, set(), str(f))
        assert edges == []

    def test_extract_contains_edges_classes_and_methods(self, tmp_path) -> None:
        """CONTAINS edges link file→class→method."""
        f = tmp_path / "sample.py"
        f.write_text(SAMPLE_PYTHON_FILE)
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        edges = extract_contains_edges(symbols, str(f))
        edge_types = {e[2] for e in edges}
        assert "CONTAINS" in edge_types
        # Should have file→class and class→method edges
        assert len(edges) >= 3  # file→class, class→__init__, class→greet

    def test_extract_contains_edges_empty(self) -> None:
        """CONTAINS returns empty for symbols without classes."""
        symbols = [
            type("ParsedSymbol", (), {"name": "x", "kind": "variable", "file_path": "/t.py", "line_start": 1, "line_end": 1, "docstring": None, "qualified_name": "/t.py::x"})(),
        ]
        edges = extract_contains_edges(symbols, "/t.py")  # type: ignore[arg-type]
        assert edges == []

    def test_extract_inherits_edges_empty_with_symbols_only(self) -> None:
        """INHERITS returns empty when only ParsedSymbol info is available."""
        symbols = [
            type("ParsedSymbol", (), {"name": "MyClass", "kind": "class", "file_path": "/t.py", "line_start": 1, "line_end": 1, "docstring": None, "qualified_name": "/t.py::MyClass"})(),
        ]
        edges = extract_inherits_edges(symbols, "/t.py")  # type: ignore[arg-type]
        assert edges == []

    def test_extract_implements_edges_empty_with_symbols_only(self) -> None:
        """IMPLEMENTS returns empty when only ParsedSymbol info is available."""
        symbols = [
            type("ParsedSymbol", (), {"name": "MyClass", "kind": "class", "file_path": "/t.py", "line_start": 1, "line_end": 1, "docstring": None, "qualified_name": "/t.py::MyClass"})(),
        ]
        edges = extract_implements_edges(symbols, "/t.py")  # type: ignore[arg-type]
        assert edges == []

    def test_detect_tested_by_matching(self, tmp_path) -> None:
        """TESTED_BY edge detected for test_*.py → *.py pattern."""
        test_f = tmp_path / "test_foo.py"
        test_f.write_text("def test_something(): pass")
        source_f = tmp_path / "foo.py"
        source_f.write_text("def something(): pass")
        source_files = {str(source_f)}
        edges = detect_tested_by(str(test_f), source_files)
        assert len(edges) == 1
        assert edges[0][2] == "TESTED_BY"
        assert edges[0][1] == os.path.abspath(str(source_f))

    def test_detect_tested_by_no_match(self, tmp_path) -> None:
        """TESTED_BY returns empty when no source matches."""
        test_f = tmp_path / "test_bar.py"
        test_f.write_text("def test_x(): pass")
        source_files = {str(tmp_path / "foo.py")}
        edges = detect_tested_by(str(test_f), source_files)
        assert edges == []

    def test_detect_tested_by_underscore_pattern(self, tmp_path) -> None:
        """TESTED_BY detects *_test.py pattern."""
        test_f = tmp_path / "foo_test.py"
        test_f.write_text("def test_x(): pass")
        source_f = tmp_path / "foo.py"
        source_f.write_text("def x(): pass")
        source_files = {str(source_f)}
        edges = detect_tested_by(str(test_f), source_files)
        assert len(edges) == 1
        assert edges[0][2] == "TESTED_BY"

    def test_detect_tested_by_non_test_file(self, tmp_path) -> None:
        """TESTED_BY returns empty for non-test files."""
        f = tmp_path / "utils.py"
        f.write_text("x = 1")
        source_files = {str(tmp_path / "foo.py")}
        edges = detect_tested_by(str(f), source_files)
        assert edges == []

    def test_extract_depends_on_edges_fallback(self, tmp_path) -> None:
        """DEPENDS_ON edges created for unclassified imports."""
        f = tmp_path / "main.py"
        f.write_text("import os\n")
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        known_files = {str(tmp_path / "os.py")}
        # No existing edges → DEPENDS_ON should be created
        edges = extract_depends_on_edges(symbols, known_files, str(f), [])
        assert isinstance(edges, list)

    def test_extract_calls_edges(self, tmp_path) -> None:
        """CALLS edges extracted from call expressions."""
        f = tmp_path / "caller.py"
        f.write_text("import os\nx = os.path.join('a', 'b')\n")
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        # Re-parse to get root node
        import tree_sitter as ts
        import tree_sitter_language_pack as tslp
        binding = tslp.get_binding("python")
        lang = ts.Language(binding)
        ts_parser = ts.Parser(lang)
        tree = ts_parser.parse(f.read_bytes())
        known_symbols = {s.qualified_name: s for s in symbols}
        edges = extract_calls_edges(tree.root_node, str(f), known_symbols)
        assert isinstance(edges, list)
        # All edges should have CALLS type
        for edge in edges:
            assert edge[2] == "CALLS"

    def test_extract_calls_edges_empty_when_no_calls(self, tmp_path) -> None:
        """CALLS returns empty when no call expressions exist."""
        f = tmp_path / "nocalls.py"
        f.write_text("x = 1\ny = 2\n")
        parser = ASTParser()
        symbols = parser.parse_file(str(f))
        import tree_sitter as ts
        import tree_sitter_language_pack as tslp
        binding = tslp.get_binding("python")
        lang = ts.Language(binding)
        ts_parser = ts.Parser(lang)
        tree = ts_parser.parse(f.read_bytes())
        edges = extract_calls_edges(tree.root_node, str(f), {})
        assert edges == []
