# Phase 3 Context — File Graph

## Phase Goal
Implement AST parsing with tree-sitter, NetworkX graph building, SHA-256 change detection, and MCP tools for tracking and querying file relationships. This phase mirrors the exact patterns from code-review-graph.

---

## Decisions

### Decision 1: Tree-Sitter Library
- **Decision:** Use `tree-sitter-language-pack` (multi-language, auto-detect from file extension)
- **Rationale:** Already declared in `pyproject.toml` dependencies. Matches code-review-graph's multi-language support philosophy. Auto-detection from file extension eliminates manual language specification.
- **Alternatives considered:** `tree-sitter` + `tree-sitter-python` only, regex-based Python parsing
- **Trade-offs:** Larger install, potential Windows compatibility risk (R2), but aligns with project vision. If installation fails, fall back to Python-only regex parsing for MVP.

### Decision 2: Qualified Name Format
- **Decision:** `/absolute/path/file.py::ClassName.method_name` (exact code-review-graph format)
- **Rationale:** Consistent with code-review-graph's proven pattern. Absolute paths eliminate ambiguity. `::` delimiter is clear and unambiguous. Supports nested symbols (class.method, class.inner_class.method).
- **Alternatives considered:** Relative paths, NetworkX node IDs as primary identifiers
- **Trade-offs:** Absolute paths are longer but guarantee uniqueness. Can derive relative paths for display later.

### Decision 3: Edge Types Scope
- **Decision:** Implement all 7 edge types: `CALLS`, `IMPORTS_FROM`, `INHERITS`, `IMPLEMENTS`, `CONTAINS`, `TESTED_BY`, `DEPENDS_ON`
- **Rationale:** These are the exact edge types from code-review-graph research. Each captures a distinct relationship:
  - `IMPORTS_FROM`: File/module imports
  - `CALLS`: Function/method invocations
  - `INHERITS`: Class inheritance relationships
  - `IMPLEMENTS`: Interface/protocol implementations
  - `CONTAINS`: File → class → function hierarchy
  - `TESTED_BY`: Test file → source file mapping
  - `DEPENDS_ON`: General dependency relationships
- **Alternatives considered:** Subset (IMPORTS_FROM + DEPENDS_ON only), free-form edge types
- **Trade-offs:** More edge types = more parsing complexity, but richer graph analysis. All 7 are documented in project research.

### Decision 4: Graph Storage Format
- **Decision:** NetworkX `DiGraph` in-memory, JSON on-disk (`./data/file_graph.json`)
- **Rationale:** Matches existing `file_graph.py` placeholder design. JSON is human-readable, easy to debug, and requires no additional dependencies. NetworkX provides built-in `node_link_data()` for JSON serialization.
- **Alternatives considered:** GraphML, GML, SQLite with recursive CTEs
- **Trade-offs:** JSON doesn't preserve node/edge attribute types as well as GraphML, but is simpler. SQLite CTEs enable graph traversal queries but add complexity. For weekend scope, JSON is sufficient.

### Decision 5: SHA-256 Change Detection Granularity
- **Decision:** Per-file hashing (entire file content)
- **Rationale:** Simple, correct, and sufficient for detecting any change. Each `FileNode` stores its `file_hash` attribute. Matches code-review-graph pattern. Per-symbol hashing adds parsing overhead for marginal benefit.
- **Alternatives considered:** Per-symbol hashing, line-level diff tracking
- **Trade-offs:** Per-file means any change triggers re-parsing of the entire file. For typical weekend project scope (hundreds of files), this is negligible.

### Decision 6: Incremental Update Strategy
- **Decision:** Incremental — use SHA-256 index to detect changes and only re-parse modified files
- **Rationale:** Matches code-review-graph design and Phase 3 roadmap (task 3.7). `update_graph(directory, changed_files)` only re-parses changed files, preserving unchanged graph portions. Far more efficient than full rebuilds for active projects.
- **Alternatives considered:** Full rebuild on every call, hybrid (full for <50 files, incremental for larger)
- **Trade-offs:** Incremental logic is more complex but pays off immediately. Initial `build_graph` is always a full operation.

### Decision 7: MCP Tool Response Format
- **Decision:** JSON strings via `json.dumps(indent=2)` — consistent with Phase 2 pattern
- **Rationale:** Matches established pattern from `chat_store.py` and `mcp_server.py`. All MCP tools return structured JSON with metadata + data. Easy for programmatic clients to parse.
- **Alternatives considered:** Formatted text, both JSON + text
- **Trade-offs:** JSON-only means client must format for display, but this is consistent with Phase 2 tools.

---

## Architecture

### Data Flow
```
MCP Client ──→ track_files(directory) ──→ FileGraph
                                          │
                                          ├── Walk directory → detect language per file
                                          │
                                          ├── For each file:
                                          │     ├── ASTParser.parse_file() → symbols + edges
                                          │     └── SHA-256 hash → change detection
                                          │
                                          ├── Build NetworkX DiGraph
                                          │
                                          └── Save to ./data/file_graph.json

MCP Client ──→ get_file_graph(file_path) ──→ FileGraph
                                              │
                                              ├── Load graph from disk
                                              │
                                              ├── Get subgraph for file_path (dependencies + dependents)
                                              │
                                              └── Return: {file, nodes, edges, impact_summary}
```

### Module Responsibilities
| Module | Responsibility |
|--------|---------------|
| `parser.py` | `ASTParser` class — parse files with tree-sitter, extract symbols and edges |
| `file_graph.py` | `FileGraph` class — NetworkX graph, build/update/query, SHA-256 tracking, persistence |
| `mcp_server.py` | Register `track_files` and `get_file_graph` tools |

### Edge Types (7 Total)
| Edge Type | Meaning | Example |
|-----------|---------|---------|
| `IMPORTS_FROM` | File imports from another module | `from os.path import join` → `IMPORTS_FROM os.path` |
| `CALLS` | Function/method invocation | `foo.bar()` → `CALLS foo.bar` |
| `INHERITS` | Class inheritance | `class Child(Parent)` → `INHERITS Parent` |
| `IMPLEMENTS` | Interface/protocol implementation | `class MyProtocol(Protocol)` → `IMPLEMENTS Protocol` |
| `CONTAINS` | Hierarchical containment | `file.py::Class` → `CONTAINS file.py::Class.method` |
| `TESTED_BY` | Test file relationship | `test_foo.py` → `TESTED_BY foo.py` |
| `DEPENDS_ON` | General dependency | Any dependency not covered above |

### Qualified Name Schema
- **Format:** `/absolute/path/file.py::ClassName.method_name`
- **Top-level function:** `/absolute/path/file.py::function_name`
- **Class:** `/absolute/path/file.py::ClassName`
- **Method:** `/absolute/path/file.py::ClassName.method_name`
- **Module:** `/absolute/path/file.py` (no `::` suffix for module-level)

### SHA-256 Index Format
```json
{
  "/absolute/path/file.py": {
    "hash": "sha256hexstring",
    "language": "python",
    "last_modified": "ISO-8601-timestamp",
    "size_bytes": 1234
  }
}
```

### Graph JSON Format
```json
{
  "directed": true,
  "multigraph": false,
  "graph": {
    "root_path": "/absolute/path/to/project",
    "built_at": "ISO-8601-timestamp",
    "file_count": 42,
    "edge_count": 156
  },
  "nodes": [
    {
      "id": "/abs/path/file.py::ClassName.method_name",
      "file_path": "/abs/path/file.py",
      "name": "ClassName.method_name",
      "kind": "method",
      "language": "python",
      "line_start": 10,
      "line_end": 25,
      "file_hash": "sha256hexstring"
    }
  ],
  "edges": [
    {
      "source": "/abs/path/a.py::func",
      "target": "/abs/path/b.py::OtherClass.method",
      "edge_type": "CALLS"
    }
  ]
}
```

---

## File Changes Expected
| File | Change |
|------|--------|
| `src/context_memory_mcp/parser.py` | **Replace** placeholder with full tree-sitter AST parser |
| `src/context_memory_mcp/file_graph.py` | **Replace** placeholder with full NetworkX implementation |
| `src/context_memory_mcp/mcp_server.py` | **Update** `register_all()` to import parser/file_graph register functions |
| `tests/test_parser.py` | **Create** — unit tests for AST parsing |
| `tests/test_file_graph.py` | **Create** — unit tests for graph build/update/query |

---

## Risks (Phase 3 Specific)
| # | Risk | Mitigation |
|---|------|------------|
| R3.1 | `tree-sitter-language-pack` fails to install on Windows | Risk R2 from roadmap. Fallback: Python-only regex parsing for MVP. Test early in Phase 3. |
| R3.2 | Tree-sitter grammar compilation fails for certain languages | Catch ImportError, log warning, skip unsupported languages. Continue with supported ones. |
| R3.3 | Large directories cause slow parsing (1000+ files) | Incremental updates mitigate this. Add progress logging. Consider file type filtering (skip node_modules, .git, etc.). |
| R3.4 | NetworkX serialization issues with complex edge attributes | Use `node_link_data()` format. Keep edge attributes simple (strings, numbers). |

---

## Out of Scope (Phase 3)
- Leiden community detection (explicitly out of scope per ROADMAP.md)
- File watching (watchdog) — deferred to Phase 4 or post-MVP
- Multi-repo graph traversal
- Language-specific advanced parsing (e.g., TypeScript decorators, Rust macros)
- Graph visualization (D3.js)
- Execution flow analysis
- Risk scoring / refactoring suggestions
- `get_impact_set` detailed impact analysis beyond transitive closure
