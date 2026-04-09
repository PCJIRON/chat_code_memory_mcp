# Phase 3 Peer Review — File Graph

**Review Date:** 2026-04-09
**Reviewer:** Cross-AI Peer Review
**Scope:** `src/context_memory_mcp/parser.py`, `src/context_memory_mcp/file_graph.py`, `src/context_memory_mcp/mcp_server.py`, `tests/test_parser.py`, `tests/test_file_graph.py`
**Verdict:** **PASS_WITH_NOTES**

---

## Summary

Phase 3 is a solid implementation of AST parsing, file graph tracking, and MCP tool integration. The code follows the patterns established in Phase 2, tests are comprehensive (99 passing), and the architecture is sound for a personal weekend project. No critical blockers found.

**Statistics:**
- CRITICAL: 0
- MAJOR: 2
- MINOR: 4
- NIT: 3

---

## 1. Code Quality

### Readability: Good
Both `parser.py` and `file_graph.py` have clear, well-structured code. The `ASTParser` class follows a logical progression: init → detect language → parse → extract symbols. The `FileGraph` class cleanly separates file walking, node creation, edge extraction, and queries. Function names are descriptive (`_walk_code_files`, `extract_imports_edges`, `get_impact_set`).

### Maintainability: Good
- Edge extraction functions are module-level (not methods), making them independently testable and reusable.
- The `register(mcp)` pattern from Phase 2 is reused consistently.
- Type hints are thorough: `list[ParsedSymbol]`, `dict[str, Any]`, `list[tuple[str, str, str]]`.
- `from __future__ import annotations` used consistently.

### Consistency: Good
- Naming conventions match Phase 2: `get_graph()` singleton, `reset_graph()` for testing, `register(mcp)` for tool registration.
- JSON output uses `json.dumps(indent=2)` consistently.
- All edge types use the `"edge_type"` attribute on NetworkX edges.

### MAJOR — Edge extraction functions use fragile string-matching for import resolution [MAJOR]
**File:** `src/context_memory_mcp/parser.py`, lines 270-293 (`extract_imports_edges`)
The function matches imports to known files using substring matching on lowercase names:
```python
import_name = sym.name.lower()
for known in known_files:
    known_base = os.path.splitext(os.path.basename(known))[0].lower()
    if known_base in import_name or import_name in known_base:
```
This produces false positives. For example, `import os` would match a file named `cosmetics.py` (because `"os" in "cosmetics"`). Similarly, `from pathlib import Path` has import text `"from pathlib import Path"`, and a file named `path_utils.py` would match because `"path" in "from pathlib import path"`.

**Impact:** The `break` after first match limits damage to one false positive per import, but incorrect edges still pollute the graph. For a personal tool analyzing a small codebase, this is unlikely to cause real harm, but the algorithm does not scale well to larger projects.

**Recommendation:** Parse the import statement properly — extract the module name from the AST node's named children rather than matching raw text. For `import_statement`, the `name` field contains the module. For `import_from_statement`, the `module` field contains it.

### MINOR — `import os` inside `qualified_name` property [MINOR]
**File:** `src/context_memory_mcp/parser.py`, lines 52-54
```python
@property
def qualified_name(self) -> str:
    import os
    abs_path = os.path.abspath(self.file_path)
```
The `import os` is inside the property method but `os` is already imported at module level (line 9). This redundant import is harmless but confusing.

**Recommendation:** Remove the inner `import os` — use the module-level import.

### MINOR — Repeated `import logging` inside exception handlers [MINOR]
**File:** `src/context_memory_mcp/parser.py`, lines 117, 127, 165, 185
Each exception handler does `import logging` then `logging.warning(...)`. This works but is unconventional. The import should be at module level.

**Recommendation:** Add `import logging` at the top of the file alongside other imports.

### NIT — `extract_inherits_edges` and `extract_implements_edges` are no-ops [NIT]
**File:** `src/context_memory_mcp/parser.py`, lines 345-370
Both functions iterate over symbols and then do nothing — the loop body is either a comment or empty. The functions exist as "hooks for future enhancement" but currently return empty lists unconditionally.

**Assessment:** This is acceptable for MVP — the plan acknowledged these would need AST root node access. They should be documented as stubs or have a `# Stub — requires AST root node access` comment to avoid confusion.

---

## 2. Architecture

### Design Decisions: Sound
- **tree-sitter via `tree-sitter-language-pack`** — Correct choice. The `get_binding()` → `ts.Language()` → `ts.Parser()` chain avoids network dependency issues.
- **NetworkX DiGraph** — Right call. Rich API for graph operations (`ancestors`, `descendants`, `node_link_data`). Well-suited for dependency analysis.
- **SHA-256 change detection** — Efficient and reliable. The 8KB chunked reads are a good performance choice.
- **Module-level singleton** — Consistent with Phase 2's `get_store()` pattern. Works well for single-user.

### Patterns: Appropriate
- **Two-phase `build_graph()`** — Parse all files first, then extract edges. This ensures all known files are available for import matching.
- **In-place `dirnames[:]` filtering** — Correct approach for skipping directories during `os.walk()`.
- **`register(mcp)` pattern** — Excellent reuse of Phase 2's convention. Clean separation of concerns.

### Scalability: Good with caveats

### MAJOR — `update_graph` re-parses files twice for changed files [MAJOR]
**File:** `src/context_memory_mcp/file_graph.py`, lines 364-420
In `update_graph()`, changed files are parsed twice:
1. First pass (lines 364-398): Parse to create nodes and update hash index
2. Second pass (lines 401-420): Parse again to re-extract edges

This is because the symbols from the first pass are not retained for edge extraction in the second pass.

**Impact:** 2x parsing cost for changed files. For a personal project with small files, this is negligible. But for a 500-file codebase with incremental updates, this doubles the update time.

**Recommendation:** Store symbols from the first pass and reuse them for edge extraction:
```python
# In the first loop:
all_symbols[f] = symbols  # Already done for new files
# In the second loop:
symbols = all_symbols.get(f) or self._parser.parse_file(f)
```

### MINOR — `get_file_graph_tool` loads from disk on empty graph, but does not update the singleton [MINOR]
**File:** `src/context_memory_mcp/file_graph.py`, lines 473-481
```python
if graph.graph.number_of_nodes() == 0:
    try:
        default_path = os.path.join(graph.root_path, "data", "file_graph.json")
        graph = FileGraph.load(default_path)  # Local variable, not the singleton
```
The loaded graph is assigned to a local variable `graph`, not to the singleton `_graph`. Subsequent calls to `get_file_graph_tool` will still see an empty singleton and attempt to reload from disk every time.

**Impact:** Repeated disk reads for `get_file_graph` when the singleton hasn't been initialized via `track_files`. Not a correctness bug (the tool still works), but a performance waste.

**Recommendation:** Either update the singleton (`global _graph; _graph = loaded`) or cache the loaded graph at module level.

### NIT — `_hash_index` uses `dict[str, dict[str, Any]]` but stores redundant data [NIT]
**File:** `src/context_memory_mcp/file_graph.py`, lines 166-171
The `_hash_index` stores `hash`, `language`, `size_bytes`, and `last_modified` — all of which are also stored as NetworkX node attributes. This duplication is intentional (the index is for change detection, the node attributes are for graph queries), but worth noting.

---

## 3. Tests

### Coverage: Excellent
99 tests across two files:
- `test_parser.py`: 27 tests — ParsedSymbol (6), ASTParser init (3), language detection (6), parse_file (8), parse_content (2), get_imports (2), edge extraction (10)
- `test_file_graph.py`: 72 tests — FileNode (7), FileGraph init (3), walk code files (3), build_graph (7), queries (5), singleton (3), change detection (10), persistence (7), query methods (6), MCP registration (6)

### Quality: Good
- `tmp_path` fixture ensures test isolation throughout.
- `reset_graph()` used in singleton tests to prevent cross-test pollution.
- Tests verify structure, not just "no exception" — e.g., checking edge types, node counts, hash lengths.
- Round-trip persistence tests verify node/edge counts and hash index equality.
- Line number type preservation test (`isinstance(loaded_node['line_start'], int)`) is excellent — catches JSON serialization bugs.

### Edge Cases: Well-covered
- Empty directories, empty graphs, nonexistent files
- Syntax errors in parsed files
- Removed files during update
- Non-test files for `detect_tested_by`
- Unknown extensions for language detection

### MINOR — `test_extract_calls_edges` requires tree-sitter imports in test file [MINOR]
**File:** `tests/test_parser.py`, lines 405-422
The test directly imports `tree_sitter` and `tree_sitter_language_pack` to construct a parser and get the root node:
```python
import tree_sitter as ts
import tree_sitter_language_pack as tslp
binding = tslp.get_binding("python")
lang = ts.Language(binding)
ts_parser = ts.Parser(lang)
tree = ts_parser.parse(f.read_bytes())
```
This duplicates the parser initialization logic from `ASTParser._init_parser()` and creates a tight coupling to tree-sitter's internal API. If the tree-sitter API changes, this test breaks independently of the production code.

**Recommendation:** Consider adding a `parse_file_with_tree()` method or exposing the tree from `parse_file()` so tests don't need to duplicate parser setup. Alternatively, this is acceptable for a personal project since the test correctly validates the edge extraction function.

### MINOR — No test for `extract_calls_edges` with actual CALLS edge creation [MINOR]
**File:** `tests/test_parser.py`, lines 405-422
The test for `extract_calls_edges` creates a file with `os.path.join('a', 'b')` call, but the `known_symbols` dict is built from the same file's parsed symbols (which only include `import os`). The `os.path.join` call won't match any known symbol because `os` is a stdlib module, not in the graph. The test only verifies that the function returns a list — not that it actually produces CALLS edges.

**Recommendation:** Add a test with two files in the same project where one calls a function from the other, verifying CALLS edges are actually created.

### NIT — `test_mcp_server_register_all_includes_graph` has no assertions [NIT]
**File:** `tests/test_file_graph.py`, lines 752-757
```python
def test_mcp_server_register_all_includes_graph(self) -> None:
    from context_memory_mcp.mcp_server import register_all
    # Should not raise any import or registration errors
    register_all()
```
This is an "import smoke test" — it passes if no exception is raised. No explicit assertion. This is acceptable for registration tests, but worth noting.

---

## 4. Documentation

### Module Docstrings: Good
All three source files have clear module-level docstrings. `parser.py` describes its purpose and dependency. `file_graph.py` explains NetworkX usage. `mcp_server.py` documents the `register(mcp)` pattern.

### Docstrings: Good
All public classes and methods have docstrings with Args/Returns sections. `ParsedSymbol` has attribute documentation. `FileNode` documents its SHA-256 hashing approach.

### Inline Comments: Good
- `# In-place filtering to skip SKIP_DIRS` — explains the `dirnames[:]` pattern.
- `# Skip if inside a class` — clarifies the line range check.
- `# Re-parse changed files that still exist` — documents the two-pass update logic.

### NIT — Edge extraction functions lack usage examples in docstrings [NIT]
**File:** `src/context_memory_mcp/parser.py`, lines 265-400
The seven edge extraction functions have docstrings but no examples showing expected input/output. For instance, `extract_imports_edges` could benefit from:
```
Example:
    >>> symbols = [ParsedSymbol("import os", "import", "/a.py", 1, 1)]
    >>> extract_imports_edges(symbols, {"/b/os.py"}, "/a.py")
    [('/a.py', '/b/os.py::os', 'IMPORTS_FROM')]
```
**Impact:** Low — the functions are straightforward, and tests serve as examples.

---

## 5. Security

### Input Validation: MINOR concern
- **Path traversal in MCP tools:** `track_files(directory)` and `get_file_graph(file_path)` accept arbitrary paths from MCP clients. No validation is performed — a client could pass `../../etc/passwd` or `C:\Windows\System32`. For a personal local-only tool, this is acceptable, but worth noting.
- **File reading in `parse_file()`:** Opens files in binary mode (`"rb"`) — correct approach. No encoding injection risk.
- **`FileNode.compute_hash()`:** Reads files in 8KB chunks — no memory exhaustion risk from large files.

### Data Protection: Good
- All data stored locally — no cloud APIs, no network calls.
- No credentials or tokens in code.
- Graph JSON file contains only file paths, symbol names, and line numbers — no source code content.

### MCP Tool Safety: Good
- `track_files` and `get_file_graph` are read-only analysis tools.
- No `eval()`, `exec()`, or `subprocess` calls.
- Error responses use `json.dumps({"error": "..."})` — no stack trace leakage.

### MINOR — `get_file_graph_tool` error message reveals file path structure [MINOR]
**File:** `src/context_memory_mcp/file_graph.py`, line 479
```python
{"error": "No graph data available. Run track_files first."}
```
This is a generic message — good. No path information leaked. However, the `get_subgraph()` method returns empty results (not errors) for unknown files, which could be used to probe for file existence. For a personal tool, this is not a security concern.

---

## 6. Performance

### Parsing: Good
- Tree-sitter parsing is fast (sub-millisecond per file for typical Python files).
- Files opened in binary mode — no encoding overhead.
- Graceful error handling prevents crashes on malformed files.

### Graph Building: Acceptable
- Two-phase approach (parse all, then extract edges) is correct but means all files are held in memory during build. For 500 files, this is fine.
- `_walk_code_files` uses generator pattern — memory efficient for directory traversal.
- `SKIP_DIRS` and `CODE_EXTENSIONS` as `frozenset` — correct O(1) lookup.

### Change Detection: Good
- SHA-256 with 8KB chunks — efficient for large files.
- `has_changed()` is O(1) dictionary lookup + single file hash.
- `update_graph()` correctly skips unchanged files.

### MINOR — `get_impact_set` calls `nx.ancestors()` per file without batching [MINOR]
**File:** `src/context_memory_mcp/file_graph.py`, lines 312-322
```python
for cf in changed_files:
    cf_abs = os.path.abspath(cf)
    if cf_abs in self.graph:
        ancestors = nx.ancestors(self.graph, cf_abs)
```
Each `nx.ancestors()` call performs a BFS/DFS traversal. For N changed files, this is N traversals. If files share common dependents, the same nodes are visited multiple times.

**Recommendation:** Collect all changed file nodes first, then do a single multi-source BFS from all of them. For a personal project with small graphs, this is not a practical concern.

### NIT — `get_subgraph` iterates all edges to find relevant ones [NIT]
**File:** `src/context_memory_mcp/file_graph.py`, lines 281-290
```python
edges = [
    (s, t, self.graph[s][t])
    for s, t in self.graph.edges()
    if s in node_set or t in node_set
]
```
This iterates ALL edges in the graph and filters. For a 500-file project with thousands of edges, this is O(E). NetworkX supports subgraph extraction: `self.graph.subgraph(node_set)` would be more efficient.

**Impact:** Minor for current scale. Could matter for large codebases.

---

## Comparison with Phase 2 Review Recommendations

Phase 2's review identified several recommendations for Phase 3. Here's the status:

| Phase 2 Recommendation | Phase 3 Status |
|---|---|
| **Add input validation to `store_messages()`** (MINOR) | **Not addressed** — Out of scope for Phase 3 (Phase 2 issue) |
| **Add test for empty messages batch** (MINOR) | **Not addressed** — Out of scope for Phase 3 (Phase 2 issue) |
| **Remove unused `datetime` import from tests** (NIT) | **Not addressed** — Out of scope for Phase 3 (Phase 2 issue) |
| **Plan for `list_sessions()` scalability** (MAJOR) | **Not addressed** — Deferred to Phase 4 as recommended |
| **Add `prune_sessions()` method** (MAJOR) | **Not addressed** — Deferred to Phase 4 as recommended |

Phase 2's recommendations were correctly scoped as "during Phase 3" or "defer to Phase 4." None were blocking for Phase 3 to begin. The Phase 3 implementation does not make Phase 2's issues worse.

### New observations for Phase 2/3 integration:
- Phase 3's `register_all()` correctly imports both Phase 2 (`chat_store`) and Phase 3 (`file_graph`) modules. No circular import issues.
- Both phases use the same singleton pattern (`get_store()` / `get_graph()`) and `register(mcp)` convention — good architectural consistency.

---

## Findings Summary

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 0 | None |
| MAJOR | 1 | Fragile string-matching in `extract_imports_edges` (false positives) |
| MAJOR | 1 | `update_graph` parses changed files twice |
| MINOR | 1 | Redundant `import os` inside `qualified_name` property |
| MINOR | 1 | Repeated `import logging` inside exception handlers |
| MINOR | 1 | `get_file_graph_tool` loads from disk but doesn't update singleton |
| MINOR | 1 | `get_impact_set` calls `nx.ancestors()` per file without batching |
| NIT | 1 | `extract_inherits_edges` and `extract_implements_edges` are no-op stubs |
| NIT | 1 | `_hash_index` duplicates data already in NetworkX node attributes |
| NIT | 1 | `get_subgraph` iterates all edges instead of using `graph.subgraph()` |

---

## Recommendations for Phase 4

### Before Starting Phase 4 (Low Effort)
1. **Fix redundant `import os` in `qualified_name`** (MINOR). One-line removal.
2. **Move `import logging` to module level in `parser.py`** (MINOR). Clean up repeated imports.
3. **Update singleton in `get_file_graph_tool` after disk load** (MINOR). Prevents repeated disk reads.

### During Phase 4
4. **Improve import matching in `extract_imports_edges`** (MAJOR). Parse module names from AST nodes instead of substring matching on raw text. This will reduce false positives as the codebase grows.
5. **Eliminate double-parsing in `update_graph`** (MAJOR). Retain symbols from first pass for edge extraction.

### Defer
6. **Batch `nx.ancestors()` calls in `get_impact_set`** (MINOR). Use multi-source BFS.
7. **Use `graph.subgraph()` in `get_subgraph`** (NIT). More efficient edge filtering.

---

## Overall Assessment

Phase 3 is well-executed. The AST parser correctly extracts symbols from Python files, the file graph tracks meaningful relationships (imports, containment, test coverage), and the MCP tools are cleanly integrated. The 99-test suite provides strong coverage including edge cases like syntax errors, removed files, and round-trip persistence.

The two MAJOR findings (fragile import matching, double-parsing in update) are real issues but have limited practical impact for a personal weekend project. The import matching produces occasional false positives but the `break` after first match limits damage. The double-parsing doubles update cost but updates are already incremental (only changed files).

**Verdict: PASS_WITH_NOTES.** Phase 3 is ready to ship. The MAJOR findings should be tracked for Phase 4 but are not blocking.
