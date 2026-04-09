---
phase: 3
plan: 01
type: feature
wave: 1
depends_on: []
---

## Objective
Implement tree-sitter AST parsing, NetworkX file graph with SHA-256 change detection, and register `track_files` + `get_file_graph` MCP tools.

## Context
- Phase 1 & 2 are COMPLETE and SHIPPED
- Placeholders exist at `src/context_memory_mcp/parser.py` and `src/context_memory_mcp/file_graph.py`
- MCP tool registration follows the `register(mcp: FastMCP)` pattern established in Phase 2 (`chat_store.py`)
- Project uses `src/context_memory_mcp/` package layout
- Environment: Windows, Python 3.13.7, pip-based venv
- Per 3-CONTEXT.md: 7 edge types (CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON), per-file SHA-256 hashing, NetworkX DiGraph with JSON persistence at `./data/file_graph.json`, qualified name format `/abs/path/file.py::ClassName.method_name`

## Waves

### Wave 1 — Parser Foundation (Plans 1-3)
- T01-T03: Implement `ASTParser` with tree-sitter, language detection, and symbol extraction
- Must be committed together: ParsedSymbol + ASTParser form a single cohesive unit

### Wave 2 — Graph Foundation (Plans 4-7)
- T04-T07: Implement `FileGraph` with NetworkX, SHA-256 tracking, build/update logic
- Can be done after Wave 1 is complete; `FileGraph` depends on `ASTParser`

### Wave 3 — Persistence & MCP Integration (Plans 8-10)
- T08-T10: Graph save/load, MCP tool registration, integration
- Depends on Waves 1 & 2 being complete

## Tasks

### Wave 1: Parser Foundation

#### T01 — Implement ParsedSymbol data class
**Description:** Replace placeholder `ParsedSymbol` class in `parser.py` with full implementation. Store: `name`, `kind`, `file_path`, `line_start`, `line_end`, `docstring`, and add `qualified_name` property (`/abs/path/file.py::symbol_name`). Include `to_dict()` serialization method.
**Success Criteria:**
- [ ] `ParsedSymbol` constructor accepts all 6 attributes
- [ ] `qualified_name` property returns correct format with `::` delimiter (e.g., `C:\project\file.py::ClassName.method`)
- [ ] `to_dict()` returns serializable dict with all fields
- [ ] Unit test: create symbol, verify qualified_name format, verify to_dict output
**Dependencies:** None
**Estimated Commit Scope:** `src/context_memory_mcp/parser.py` (ParsedSymbol class only), `tests/test_parser.py` (ParsedSymbol tests)
**Commit Message:** `[GSD-3-01-T01] Implement ParsedSymbol data class with qualified_name property`

#### T02 — Implement language detection and tree-sitter initialization
**Description:** Implement `ASTParser.__init__()` and `detect_language()` method. Use `tslp.detect_language_from_path()` (content-based, confirmed working) with file extension fallback (`.py` → `python`). Initialize parser using `tslp.get_binding("python")` → `ts.Language(binding)` → `ts.Parser(lang)` pattern — **DO NOT use `get_language()` or `get_parser()` as they require network downloads that fail**. Handle ImportError gracefully (log warning, set `language = "unsupported"`).
**Success Criteria:**
- [ ] `detect_language_from_path()` correctly identifies `.py` files as `"python"`
- [ ] File extension fallback works when content detection fails
- [ ] `get_binding("python")` → `ts.Language()` → `ts.Parser()` chain succeeds without network
- [ ] Unknown extensions return `"unsupported"` without crashing
- [ ] ImportError for tree-sitter-language-pack is caught and logged
- [ ] Unit test: detect_language for .py, .ts, .js, .unknown
**Dependencies:** T01
**Estimated Commit Scope:** `src/context_memory_mcp/parser.py` (ASTParser.__init__, detect_language, parser init), `tests/test_parser.py` (language detection tests)
**Commit Message:** `[GSD-3-01-T02] Implement language detection and tree-sitter initialization`

#### T03 — Implement parse_file and symbol extraction
**Description:** Implement `parse_file(file_path)` and `parse_content(content, language)`. Use tree-sitter to parse the AST, walk the tree using `_find_nodes_by_type()` (NOT the Query API which throws "Impossible pattern" errors for Python) to extract: classes, functions, methods, imports. Emit `ParsedSymbol` objects with correct 1-based line numbers (add 1 to tree-sitter's 0-based `start_point`/`end_point`). Implement `get_imports(file_path)` as a convenience method. **Handle syntax errors and encoding issues gracefully** — catch exceptions, log warning, return partial results or empty list (do NOT crash).
**Success Criteria:**
- [ ] `parse_file()` on a Python file with classes/functions returns correct symbols
- [ ] Each symbol has accurate line_start/line_end (1-based, not 0-based)
- [ ] Import statements are detected (both `import x` and `from x import y`)
- [ ] `get_imports()` returns list of imported module names
- [ ] `parse_content()` works with explicit language parameter
- [ ] **`parse_file()` on a file with syntax errors returns partial results or empty list (no crash)**
- [ ] **Encoding errors are caught and logged**
- [ ] Unit test: parse a sample Python file, verify symbols match expected output
- [ ] Unit test: parse file with intentional syntax errors, verify graceful degradation
**Dependencies:** T02
**Estimated Commit Scope:** `src/context_memory_mcp/parser.py` (parse_file, parse_content, get_imports, _find_nodes_by_type, symbol extraction logic), `tests/test_parser.py` (parsing tests with sample files, error handling tests)
**Commit Message:** `[GSD-3-01-T03] Implement parse_file and symbol extraction with tree-sitter`

### Wave 2: Graph Foundation

#### T04 — Implement FileNode data class
**Description:** Replace placeholder `FileNode` class in `file_graph.py` with full implementation. Store: `path`, `language`, `size_bytes`, `last_modified`, `file_hash`. Implement `to_dict()` serialization. Add `update_hash(content)` method to compute SHA-256 using chunked reads (8KB chunks, 4x faster). **Can be executed in parallel with Wave 1 (T01–T03) since it's in a different file with no dependencies.**
**Success Criteria:**
- [ ] `FileNode` constructor accepts all 5 attributes
- [ ] `update_hash()` computes correct SHA-256 hex digest using chunked reads
- [ ] `to_dict()` returns serializable dict
- [ ] Unit test: create node, verify hash computation, verify serialization
**Dependencies:** None (can be done in parallel with Wave 1)
**Estimated Commit Scope:** `src/context_memory_mcp/file_graph.py` (FileNode class only), `tests/test_file_graph.py` (FileNode tests)
**Commit Message:** `[GSD-3-01-T04] Implement FileNode data class with SHA-256 hashing`

#### T05 — Implement edge extraction logic
**Description:** Add edge extraction helpers in `parser.py`. Given parsed AST nodes and a file list, determine edges:
- `IMPORTS_FROM`: Match `import_statement` and `import_from_statement` nodes to known files in the graph
- `CONTAINS`: File → class, class → method hierarchy (from `class_definition` and `function_definition` parent-child relationships)
- `CALLS`: Detect function calls via `call` nodes — extract `function` field text
- `INHERITS`: Detect base classes via `superclasses` field on `class_definition` nodes
- `IMPLEMENTS`: Detect Protocol/ABC implementations (class inherits from `Protocol` or `ABC`)
- `TESTED_BY`: Match `test_*.py` / `*_test.py` to corresponding source files (only when target file exists in graph)
- `DEPENDS_ON`: General fallback for any dependency not covered above
**Success Criteria:**
- [ ] Given 2 Python files where A imports B, edge `IMPORTS_FROM` is created
- [ ] CONTAINS edges link file → classes → methods
- [ ] Given a class inheriting from another, edge `INHERITS` is created
- [ ] Given `test_foo.py` and `foo.py`, edge `TESTED_BY` is created (only if `foo.py` exists in graph)
- [ ] CALLS edges capture function/method invocations
- [ ] Each edge has `edge_type` attribute matching one of the 7 types
- [ ] Unit test: create 2 sample files, verify edges are correct
**Dependencies:** T03 (needs parse_file to work)
**Estimated Commit Scope:** `src/context_memory_mcp/parser.py` (edge extraction helpers), `tests/test_parser.py` (edge extraction tests)
**Commit Message:** `[GSD-3-01-T05] Implement edge extraction logic for all 7 edge types`

#### T06 — Implement FileGraph class skeleton and build_graph
**Description:** Replace placeholder `FileGraph` class. Initialize with `root_path` and empty `networkx.DiGraph`. Implement:
- `add_node(node_id, **attrs)` / `add_edge(source, target, edge_type)` — basic NetworkX wrappers
- `build_graph(directory)`: Walk directory using `os.walk()` with in-place `dirnames[:]` filtering (skip `.git`, `__pycache__`, `.venv`, `node_modules`, `dist`, `build`, `.pytest_cache`), filter by `CODE_EXTENSIONS`, for each source file: parse with `ASTParser`, create `FileNode`, add to graph, extract edges, add to graph. Store SHA-256 index in `self._hash_index`. Log progress: `"Parsed {n}/{total} files..."`. Return summary `{file_count, node_count, edge_count, built_at}`.
**Success Criteria:**
- [ ] `build_graph()` walks directory and parses all supported files
- [ ] Graph nodes have correct attributes (file_path, name, kind, line_start, line_end, file_hash)
- [ ] Graph edges have `edge_type` attribute
- [ ] SHA-256 index is populated in `self._hash_index`
- [ ] Summary dict has correct counts
- [ ] **Progress logging: logs start count, completion summary with totals**
- [ ] Unit test: build graph from test fixtures, verify node/edge counts
**Dependencies:** T03, T04, T05
**Estimated Commit Scope:** `src/context_memory_mcp/file_graph.py` (FileGraph class, build_graph, walk_code_files helper), `tests/test_file_graph.py` (build_graph tests)
**Commit Message:** `[GSD-3-01-T06] Implement FileGraph with NetworkX DiGraph and build_graph`

#### T07 — Implement SHA-256 change detection and incremental update
**Description:** Implement `update_graph(directory, changed_files: list[str] | None = None)`:
1. If `changed_files` is None: scan directory, compare SHA-256 index to detect changes using `has_changed(file_path)` helper
2. For each changed file: remove old nodes/edges from graph, re-parse, add updated nodes/edges
3. For unchanged files: preserve existing graph nodes/edges
4. Update SHA-256 index
5. Return summary with `{added, removed, updated, unchanged, total_files}`
**Success Criteria:**
- [ ] `has_changed()` returns True when file content differs from stored hash
- [ ] `update_graph()` with no changes returns 0 updates
- [ ] `update_graph()` with 1 changed file only re-parses that file
- [ ] Removed files are cleaned up (nodes and edges removed from graph)
- [ ] Unit test: build graph, modify 1 file, update, verify only 1 file was re-parsed
**Dependencies:** T06
**Estimated Commit Scope:** `src/context_memory_mcp/file_graph.py` (update_graph, has_changed, SHA-256 comparison), `tests/test_file_graph.py` (incremental update tests)
**Commit Message:** `[GSD-3-01-T07] Implement SHA-256 change detection and incremental update`

### Wave 3: Persistence & MCP Integration

#### T08 — Implement graph persistence (save/load)
**Description:** Implement `FileGraph.save(path)` and `FileGraph.load(path)`:
- `save()`: Use `networkx.node_link_data(G)` (NO `attrs` parameter — removed in NetworkX 3.x) to serialize graph + SHA-256 index to JSON at `./data/file_graph.json` (or custom path)
- `load()`: Class method that reads JSON, reconstructs DiGraph with `networkx.node_link_graph(data)`, restores SHA-256 index, returns `FileGraph` instance
- Ensure `ensure_data_dir()` creates `./data/` directory if it doesn't exist
**Success Criteria:**
- [ ] `save()` writes valid JSON to `./data/file_graph.json`
- [ ] `load()` reconstructs identical graph with all node/edge attributes
- [ ] Round-trip: build → save → load → verify node/edge counts match
- [ ] `./data/` directory is created automatically if missing
- [ ] **Edge case: graph with 0 edges saves/loads correctly**
- [ ] **Edge case: line number attributes survive round-trip as integers (not strings)**
- [ ] Unit test: save graph, load it, verify equality
**Dependencies:** T06
**Estimated Commit Scope:** `src/context_memory_mcp/file_graph.py` (save, load, ensure_data_dir), `tests/test_file_graph.py` (persistence tests)
**Commit Message:** `[GSD-3-01-T08] Implement graph persistence with JSON save/load`

#### T09 — Implement graph query methods
**Description:** Add query methods to `FileGraph`:
- `get_file_nodes(file_path)`: Return all nodes belonging to a file
- `get_dependencies(file_path)`: Return files this file depends on (outgoing edges via `nx.descendants()`)
- `get_dependents(file_path)`: Return files that depend on this file (incoming edges via `nx.ancestors()`)
- `get_impact_set(changed_files)`: Return transitive closure of all files affected by changes (all ancestors of changed nodes)
- `get_subgraph(file_path)`: Return dict with `{file, nodes, edges, impact_summary}` for MCP response
**Success Criteria:**
- [ ] `get_dependencies()` returns correct list of files this file imports from
- [ ] `get_dependents()` returns correct list of files that import this file
- [ ] `get_impact_set()` returns transitive closure (all files reachable via incoming edges)
- [ ] `get_subgraph()` returns properly formatted dict for MCP response
- [ ] Unit test: build graph, query dependencies/dependents/impact set, verify correctness
**Dependencies:** T06
**Estimated Commit Scope:** `src/context_memory_mcp/file_graph.py` (query methods), `tests/test_file_graph.py` (query tests)
**Commit Message:** `[GSD-3-01-T09] Implement graph query methods (dependencies, dependents, impact set)`

#### T10 — Register track_files and get_file_graph MCP tools
**Description:** Implement `register(mcp: FastMCP)` function in `file_graph.py`:
- `track_files(directory)`: Accepts directory path, calls `build_graph()` or `update_graph()`, returns JSON summary `{status, file_count, node_count, edge_count, built_at}`
- `get_file_graph(file_path)`: Accepts file path, loads graph from disk, calls `get_subgraph()`, returns JSON `{file, nodes, edges, impact_summary}`
- Update `mcp_server.py` to uncomment and call `register_graph(mcp)` in `register_all()`
- Use `Annotated[type, Field(description="...")]` for parameter schemas (per Phase 2 pattern)
- Use `json.dumps(indent=2)` format (per 3-CONTEXT.md Decision 7)
**Success Criteria:**
- [ ] `track_files("/path/to/dir")` returns JSON with file/node/edge counts
- [ ] `get_file_graph("/path/to/file.py")` returns JSON with subgraph data
- [ ] Both tools use `json.dumps(indent=2)` format (per 3-CONTEXT.md Decision 7)
- [ ] `mcp_server.py` imports and registers graph tools without errors
- [ ] Integration test: run server, call both tools, verify JSON responses
- [ ] `pyproject.toml` includes `tree-sitter-language-pack` and `networkx` (already present)
**Dependencies:** T06, T08, T09 (T07 optional — `track_files` works with `build_graph` alone)
**Estimated Commit Scope:** `src/context_memory_mcp/file_graph.py` (register function), `src/context_memory_mcp/mcp_server.py` (uncomment registration), `tests/test_file_graph.py` or `tests/test_mcp_integration.py` (MCP tool tests)
**Commit Message:** `[GSD-3-01-T10] Register track_files and get_file_graph MCP tools`

## Verification
- [ ] All 10 tasks completed with passing unit tests
- [ ] `tree-sitter-language-pack` installs successfully on Windows (verify T02)
- [ ] `pytest tests/test_parser.py` passes (≥90% coverage on parser.py)
- [ ] `pytest tests/test_file_graph.py` passes (≥90% coverage on file_graph.py)
- [ ] `track_files` MCP tool returns valid JSON with graph summary
- [ ] `get_file_graph` MCP tool returns valid JSON with subgraph data
- [ ] Graph persistence works: build → save → load produces identical graph
- [ ] Incremental update correctly detects and re-parses only changed files
- [ ] `mcp_server.py` `register_all()` runs without import errors
- [ ] All commits follow `[GSD-3-01-T{N}]` format

## Expected Output
- `src/context_memory_mcp/parser.py` — Full ASTParser implementation with tree-sitter
- `src/context_memory_mcp/file_graph.py` — Full FileGraph implementation with NetworkX
- `src/context_memory_mcp/mcp_server.py` — Updated with graph tool registration
- `tests/test_parser.py` — Unit tests for AST parsing
- `tests/test_file_graph.py` — Unit tests for graph operations
- `./data/file_graph.json` — Persisted graph file (created at runtime)

## Implementation Notes
- **3-CONTEXT.md Decision 1**: Use `tslp.get_binding("python")` → `ts.Language()` → `ts.Parser()` pattern. **DO NOT use `get_language()` or `get_parser()` — they require network downloads that fail.** Use `tslp.detect_language_from_path()` for content-based detection (works), NOT `detect_language_from_extension()` (returns None).
- **3-CONTEXT.md Decision 2**: Qualified name format is exactly `/abs/path/file.py::ClassName.method_name` — no variations. Use absolute paths as-is (Windows: `C:\path\file.py`).
- **3-CONTEXT.md Decision 3**: All 7 edge types must be implemented. Use `_find_nodes_by_type()` manual tree walking — NOT the Query API which throws "Impossible pattern" errors for Python.
- **3-CONTEXT.md Decision 4**: Use `networkx.node_link_data()` WITHOUT `attrs` parameter (removed in NetworkX 3.x). Default `id`/`source`/`target` fields.
- **3-CONTEXT.md Decision 5**: Per-file SHA-256 hashing using chunked reads (8KB chunks, 4x faster).
- **3-CONTEXT.md Decision 6**: Incremental update is mandatory — `update_graph()` must NOT re-parse unchanged files.
- **3-CONTEXT.md Decision 7**: All MCP tool responses use `json.dumps(indent=2)` — consistent with Phase 2 pattern.
- **Risk R3.1**: If `get_binding()` fails for non-Python languages, catch exception, log warning, skip file. Graph still builds for supported languages.
- **Risk R3.3**: Skip `.git`, `__pycache__`, `.venv`, `node_modules`, `dist`, `build`, `.pytest_cache` directories. Use `dirnames[:] = [...]` in-place filtering.
- **Error Handling**: `parse_file()` must NEVER crash on syntax errors — catch exceptions, log warning, return partial/empty results.
- **Line Numbers**: Tree-sitter uses 0-based `start_point`/`end_point`. Add 1 for human-readable 1-based output.
- **File Reading**: Always open files with `"rb"` mode — tree-sitter expects bytes, not strings.
- **Singleton Pattern**: Use module-level `_graph: FileGraph | None = None` + `get_graph()` getter (same as `chat_store.py` pattern).
