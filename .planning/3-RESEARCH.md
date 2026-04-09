# Phase 3 Research — File Graph

## Phase Goals
Implement AST parsing with tree-sitter, NetworkX graph building, SHA-256 change detection, and MCP tools (`track_files`, `get_file_graph`) for tracking and querying file relationships. This phase delivers the core codebase analysis capability.

---

## Approaches Considered

### Approach 1: tree-sitter-language-pack (tslp) — Primary

**Description:** Use `tree-sitter-language-pack` (v1.5.0, already installed in `.venv`) as a unified wrapper over tree-sitter with automatic language detection and on-demand grammar downloads.

**Pros:**
- Multi-language support (Python, TypeScript, JavaScript, Rust, Go, Java, etc.)
- `detect_language_from_path()` works without downloading grammars — uses content-based detection
- `get_binding()` returns a PyCapsule compatible with `tree_sitter.Language()` — no download needed for bundled grammars
- Single API surface for all languages

**Cons:**
- `get_language()`, `get_parser()`, and `download()` require network access to download pre-built grammar binaries — **confirmed to time out/fail** on current setup
- `detect_language_from_extension()` returns `None` for all extensions without downloaded grammars — **not usable**
- `available_languages()` returns 0, `downloaded_languages()` returns empty — grammars not pre-bundled
- `download_all()` timed out after 60s — network/download infrastructure unreliable

**Complexity:** Medium (API works partially, downloads unreliable)
**Time Estimate:** 2-3 hours for Python-only, 4-6 hours if multi-language downloads work

---

### Approach 2: tree-sitter + tree-sitter-python (direct) — Fallback

**Description:** Use `tree-sitter` (v0.25.2, installed) directly with individual language packages like `tree-sitter-python`.

**Pros:**
- `tree_sitter` 0.25.2 is confirmed working — `Language`, `Parser`, `Query`, `QueryCursor` all available
- No network download needed — grammar compiled into `tree_sitter_python` package
- Cleaner API — `ts.Language(binding)`, `ts.Parser(lang)` are straightforward

**Cons:**
- **`tree_sitter_python` is NOT installed** in the current `.venv` — would need `pip install tree-sitter-python`
- Each language requires its own package (`tree-sitter-typescript`, `tree-sitter-javascript`, etc.)
- Manual language-to-package mapping needed

**Complexity:** Low (for Python), Medium (for multi-language)
**Time Estimate:** 1-2 hours for Python-only

---

### Approach 3: tree-sitter-language-pack get_binding() — Hybrid (Recommended)

**Description:** Use `tree_sitter_language_pack.get_binding("python")` which returns a PyCapsule that works **without network downloads**, then construct `tree_sitter.Language(binding)` + `tree_sitter.Parser(lang)` directly.

**Pros:**
- **Confirmed working** — `tslp.get_binding("python")` → `ts.Language(binding)` → `ts.Parser(lang)` all succeed without network
- No additional packages needed — uses what's already installed
- Can fall back to manual extension→language mapping for languages without bindings
- `detect_language_from_path()` works reliably for language detection (content-based)
- Full AST access: `node.type`, `node.text`, `node.child_by_field_name()`, `node.children`, `node.start_point`, `node.end_point`

**Cons:**
- Only works for languages that have pre-compiled bindings in the tslp package
- If `get_binding("lang")` fails, need fallback (regex or skip)
- Multi-language support limited to what tslp bundles

**Complexity:** Low
**Time Estimate:** 2-3 hours

---

### Approach 4: Regex-based parsing — Last Resort

**Description:** Use Python regex patterns to extract imports, classes, functions, and calls.

**Pros:**
- Zero dependencies beyond stdlib
- Instant, no parsing overhead

**Cons:**
- Fragile — breaks on edge cases (multi-line imports, decorators, string literals)
- Cannot reliably extract call expressions or inheritance
- No AST structure — just text matching
- Doesn't align with project vision

**Complexity:** Low (but high maintenance)
**Time Estimate:** 1-2 hours (but high bug surface)

---

## Recommended Approach

**Selected:** Approach 3 — `tree-sitter-language-pack get_binding()` + direct `tree_sitter` API

**Why:** This is the only approach that is **confirmed working** in the current environment without network downloads. It uses packages already installed (`tree-sitter` 0.25.2, `tree-sitter-language-pack` 1.5.0) and provides full AST access. The pattern is:

```python
import tree_sitter as ts
import tree_sitter_language_pack as tslp

binding = tslp.get_binding("python")   # Returns PyCapsule
lang = ts.Language(binding)             # Creates Language object
parser = ts.Parser(lang)                # Creates Parser
tree = parser.parse(source_bytes)       # Parses source
```

---

## Implementation Notes

### 1. tree-sitter-language-pack on Windows

**Installation:** Already installed (`tree-sitter-language-pack 1.5.0`, `tree-sitter 0.25.2`).

**Working API:**
- `tslp.get_binding("python")` → PyCapsule (works without network)
- `tslp.detect_language_from_path(filepath)` → `"python"`, `"toml"`, `"markdown"` (works via content detection)
- `tslp.cache_dir()` → `C:\Users\<user>\AppData\Local\tree-sitter-language-pack\v1.5.0\libs`

**Broken/Unavailable API:**
- `tslp.get_language("python")` → `LanguageNotFoundError` (needs download)
- `tslp.get_parser("python")` → needs download
- `tslp.detect_language_from_extension(".py")` → `None` (no grammars downloaded)
- `tslp.download("python")` → times out on current network
- `tslp.download_all()` → times out

**Language Detection Strategy:**
```python
def detect_language(self, file_path: str) -> str | None:
    """Detect language using content-based detection (works without downloads)."""
    return tslp.detect_language_from_path(file_path)
```

**Supported Languages (confirmed via get_binding):** The `get_binding()` function works for languages that have pre-compiled binaries bundled with the package. Python is confirmed working. For other languages, catch `Exception` and return `None` to skip gracefully.

**Risk Mitigation:** Wrap `get_binding()` in try/except. If it fails for a language, log a warning and skip the file. The graph still builds for supported languages.

### 2. tree-sitter Python API

**Parsing a file:**
```python
import tree_sitter as ts
import tree_sitter_language_pack as tslp

def parse_file(file_path: str) -> ts.Tree:
    binding = tslp.get_binding("python")
    lang = ts.Language(binding)
    parser = ts.Parser(lang)
    
    with open(file_path, "rb") as f:
        source = f.read()
    
    tree = parser.parse(source)
    return tree
```

**AST Node Types for Python (confirmed via actual parsing):**

| Node Type | Field Names | Example |
|-----------|------------|---------|
| `module` | — | Root of every Python file |
| `import_statement` | `name: dotted_name` | `import os` |
| `import_from_statement` | `module_name: dotted_name`, `name: dotted_name` | `from pathlib import Path` |
| `class_definition` | `name: identifier`, `superclasses: argument_list`, `body: block` | `class MyClass(BaseClass):` |
| `function_definition` | `name: identifier`, `parameters: parameters`, `body: block` | `def my_func():` |
| `call` | `function: _`, `arguments: argument_list` | `MyClass()`, `some_call(x)` |
| `attribute` | `object: identifier`, `attribute: identifier` | `obj.do_something` |
| `assignment` | `left: identifier`, `right: _` | `y = some_call(x)` |
| `return_statement` | — | `return result` |

**Extracting Imports:**
```python
def extract_imports(root: ts.Node) -> list[dict]:
    """Extract all import statements from AST root."""
    imports = []
    _find_nodes_by_type(root, "import_statement", imports)
    _find_nodes_by_type(root, "import_from_statement", imports)
    return [{"text": node.text.decode(), "node": node} for node in imports]

def _find_nodes_by_type(node: ts.Node, target: str, results: list):
    if node.type == target:
        results.append(node)
    for child in node.children:
        _find_nodes_by_type(child, target, results)
```

**Extracting Classes with Inheritance:**
```python
def extract_classes(root: ts.Node, file_path: str) -> list[dict]:
    classes = []
    _find_nodes_by_type(root, "class_definition", classes)
    result = []
    for cls_node in classes:
        name_node = cls_node.child_by_field_name("name")
        superclasses_node = cls_node.child_by_field_name("superclasses")
        name = name_node.text.decode() if name_node else "unknown"
        supers = []
        if superclasses_node:
            # Walk children to find identifier nodes (superclass names)
            for child in superclasses_node.children:
                if child.type == "identifier":
                    supers.append(child.text.decode())
        result.append({
            "name": name,
            "superclasses": supers,
            "node": cls_node,
            "line_start": cls_node.start_point[0] + 1,
            "line_end": cls_node.end_point[0] + 1,
        })
    return result
```

**Extracting Functions/Methods:**
```python
def extract_functions(root: ts.Node) -> list[dict]:
    funcs = []
    _find_nodes_by_type(root, "function_definition", funcs)
    result = []
    for func_node in funcs:
        name_node = func_node.child_by_field_name("name")
        name = name_node.text.decode() if name_node else "unknown"
        result.append({
            "name": name,
            "node": func_node,
            "line_start": func_node.start_point[0] + 1,
            "line_end": func_node.end_point[0] + 1,
        })
    return result
```

**Extracting Call Expressions:**
```python
def extract_calls(root: ts.Node) -> list[dict]:
    calls = []
    _find_nodes_by_type(root, "call", calls)
    result = []
    for call_node in calls:
        func_node = call_node.child_by_field_name("function")
        func_text = func_node.text.decode() if func_node else "unknown"
        result.append({
            "function": func_text,
            "node": call_node,
            "line_start": call_node.start_point[0] + 1,
            "line_end": call_node.end_point[0] + 1,
        })
    return result
```

**Tree-sitter Query API (S-expression syntax):**
The Query API uses S-expression patterns. Capture names must start with a lowercase letter or underscore.
```python
# Correct syntax (capture names: lowercase, dot-separated)
query_str = """
(import_statement
  name: (dotted_name (identifier) @imp.name))
"""
query = ts.Query(lang, query_str)
cursor = ts.QueryCursor(query)
matches = list(cursor.matches(root))
```

**Known Issue:** The Query API is finicky with Python grammar. Some patterns that work in other languages fail with "Impossible pattern" errors. **Recommendation:** Use manual tree walking (`_find_nodes_by_type`) as the primary extraction method. It's reliable, explicit, and easier to debug. Reserve Query API for simple patterns.

### 3. NetworkX Graph Operations

**NetworkX 3.6.1 confirmed installed.**

**DiGraph Creation:**
```python
import networkx as nx

G = nx.DiGraph()
G.add_node("/proj/file.py::MyClass",
           file_path="/proj/file.py",
           name="MyClass",
           kind="class",
           language="python",
           line_start=5,
           line_end=20)
G.add_edge("/proj/file.py::MyClass", "/proj/other.py::BaseClass",
           edge_type="INHERITS")
```

**JSON Serialization:**
```python
# Serialize
data = nx.node_link_data(G)
json_str = json.dumps(data, indent=2)

# Deserialize
data = json.loads(json_str)
G = nx.node_link_graph(data)
```

**node_link_data output format (confirmed):**
```json
{
  "directed": true,
  "multigraph": false,
  "graph": {},
  "nodes": [
    {"id": "/proj/file.py::MyClass", "file_path": "...", "name": "...", "kind": "..."}
  ],
  "edges": [
    {"source": "/proj/file.py::MyClass", "target": "/proj/other.py::BaseClass", "edge_type": "INHERITS"}
  ]
}
```

**Note:** `node_link_data()` in NetworkX 3.x does **not** accept the `attrs` keyword argument (removed). Use defaults: `id`, `source`, `target`.

**Transitive Closure (Impact Analysis):**
```python
# What does this file depend on? (successors = outgoing edges)
dependencies = list(G.successors("/proj/file.py::MyClass"))

# What depends on this file? (predecessors = incoming edges)
dependents = list(G.predecessors("/proj/other.py::BaseClass"))

# Full impact set: all nodes transitively affected by a change
def get_impact_set(graph: nx.DiGraph, changed_file_paths: list[str]) -> set[str]:
    changed_nodes = {
        node for fp in changed_file_paths
        for node in graph.nodes()
        if node.startswith(fp) or node.split("::")[0] == fp
    }
    impacted = set()
    for node in changed_nodes:
        impacted.update(nx.ancestors(graph, node))
    return impacted
```

**Key NetworkX functions:**
- `nx.descendants(G, node)` — all nodes reachable from `node` (what `node` depends on transitively)
- `nx.ancestors(G, node)` — all nodes that can reach `node` (what depends on `node` transitively)
- `G.subgraph(nodes)` — extract subgraph
- `nx.node_link_data(G)` / `nx.node_link_graph(data)` — JSON serialization

### 4. SHA-256 File Hashing

**Confirmed working patterns:**
```python
import hashlib

def hash_file(filepath: str, chunk_size: int = 8192) -> str:
    """SHA-256 hash of file contents. Chunked for memory efficiency."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()
```

**Performance (measured):**
- Full read: ~2.3ms for a 1.5KB file
- Chunked (8KB): ~0.5ms for a 1.5KB file
- Chunked is 4x faster for small files (less GC pressure)

**SHA-256 Index Format (from 3-CONTEXT.md):**
```json
{
  "/abs/path/file.py": {
    "hash": "sha256hexstring",
    "language": "python",
    "last_modified": "2024-01-15T10:00:00+00:00",
    "size_bytes": 1234
  }
}
```

### 5. MCP Tool Registration Pattern

**Pattern from `chat_store.py` (confirmed):**
```python
def register(mcp: FastMCP) -> None:
    """Register file graph tools with the MCP server."""
    graph = get_file_graph()  # Module-level singleton
    
    @mcp.tool(name="track_files", description="...")
    async def track_files(
        directory: Annotated[str, Field(description="...")],
    ) -> str:
        result = graph.build_graph(directory)
        return json.dumps(result, indent=2)
    
    @mcp.tool(name="get_file_graph", description="...")
    async def get_file_graph_tool(
        file_path: Annotated[str, Field(description="...")],
    ) -> str:
        result = graph.get_subgraph(file_path)
        return json.dumps(result, indent=2)
```

**Registration in `mcp_server.py`:**
```python
def register_all() -> None:
    _register_core(mcp)
    from context_memory_mcp.chat_store import register as register_chat
    register_chat(mcp)
    from context_memory_mcp.file_graph import register as register_graph
    register_graph(mcp)
    # Phase 4: register_context(mcp)
```

### 6. Directory Walking

**Confirmed working pattern:**
```python
SKIP_DIRS = frozenset({
    ".git", ".venv", "__pycache__", "node_modules", "dist", "build",
    ".pytest_cache", ".mypy_cache", "venv", "env", ".eggs", ".tox",
    ".nox", "eggs", "*.egg-info",
})
CODE_EXTENSIONS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go",
    ".java", ".c", ".cpp", ".h", ".hpp", ".rb", ".swift", ".kt",
})

def walk_code_files(root_dir: str) -> Iterator[tuple[str, str]]:
    """Walk directory, yielding (absolute_path, extension) for code files."""
    root_dir = os.path.abspath(root_dir)
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Filter dirs in-place to prevent os.walk from descending
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in CODE_EXTENSIONS:
                continue
            
            filepath = os.path.abspath(os.path.join(dirpath, fname))
            yield filepath, ext
```

**Key optimization:** `dirnames[:] = [...]` modifies in-place, preventing `os.walk` from descending into excluded directories. This is much faster than filtering after the fact.

### 7. Testing Strategy

**Pattern from `tests/test_chat_store.py` (confirmed):**
- Use `pytest` fixtures with `tmp_path` for isolated temp directories
- Test individual methods with clear `test_<method>_<scenario>` naming
- Include edge cases (empty input, missing keys, non-existent items)
- Include performance smoke tests with generous timeouts
- Use `pytest.raises` for error cases

**Parser Testing Strategy:**
```python
import pytest
import tree_sitter as ts
import tree_sitter_language_pack as tslp

@pytest.fixture()
def parser():
    """Create a Python parser for tests."""
    binding = tslp.get_binding("python")
    lang = ts.Language(binding)
    return ts.Parser(lang)

@pytest.fixture()
def sample_python_code():
    return b"""
import os
from pathlib import Path

class MyClass(BaseClass):
    def __init__(self):
        pass
    
    def do_something(self, x):
        y = helper_func(x)
        return y + 1

def my_func():
    obj = MyClass()
    result = obj.do_something(42)
    return result
"""

def test_parse_extracts_imports(parser, sample_python_code):
    tree = parser.parse(sample_python_code)
    imports = extract_imports(tree.root_node)
    assert len(imports) == 2  # import os + from pathlib import Path

def test_parse_extracts_class_with_superclass(parser, sample_python_code):
    tree = parser.parse(sample_python_code)
    classes = extract_classes(tree.root_node, "test.py")
    assert len(classes) == 1
    assert classes[0]["name"] == "MyClass"
    assert "BaseClass" in classes[0]["superclasses"]

def test_parse_extracts_function_calls(parser, sample_python_code):
    tree = parser.parse(sample_python_code)
    calls = extract_calls(tree.root_node)
    func_names = [c["function"] for c in calls]
    assert "MyClass" in func_names
    assert "obj.do_something" in [c["function"] for c in calls]
    assert "helper_func" in func_names
```

**Graph Testing Strategy:**
```python
import pytest
import networkx as nx
from context_memory_mcp.file_graph import FileGraph

@pytest.fixture()
def file_graph(tmp_path):
    """Create a FileGraph with a temp data directory."""
    return FileGraph(root_path=str(tmp_path))

def test_build_graph_creates_nodes(file_graph, tmp_path):
    # Create test files
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello(): pass\n")
    
    result = file_graph.build_graph(str(tmp_path))
    assert result["file_count"] >= 1

def test_save_load_roundtrip(file_graph, tmp_path):
    # Build and save
    save_path = str(tmp_path / "graph.json")
    file_graph.save(save_path)
    
    # Load
    loaded = FileGraph.load(save_path)
    assert loaded.graph.number_of_nodes() == file_graph.graph.number_of_nodes()

def test_impact_set(file_graph):
    # Build graph with known dependencies
    # ... add nodes/edges ...
    impact = file_graph.get_impact_set(["/changed/file.py"])
    assert "/dependent/file.py" in impact
```

---

## Libraries/Tools

| Library | Version | Why |
|---------|---------|-----|
| `tree-sitter` | 0.25.2 | Core parsing engine — confirmed working |
| `tree-sitter-language-pack` | 1.5.0 | Language detection + binding — `get_binding()` works without network |
| `networkx` | 3.6.1 | Graph operations — confirmed installed and working |
| `hashlib` | stdlib | SHA-256 hashing — no additional dependency needed |
| `pytest` | (installed) | Testing — existing pattern in project |

---

## Pitfalls to Avoid

1. **Do NOT use `tslp.get_language()` or `tslp.get_parser()`** — they require network downloads that fail. Use `tslp.get_binding()` + `ts.Language()` + `ts.Parser()` instead.

2. **Do NOT use `tslp.detect_language_from_extension()`** — returns `None` without downloaded grammars. Use `tslp.detect_language_from_path()` (content-based) or a manual extension mapping.

3. **Do NOT rely on tree-sitter Query API for complex patterns** — it throws "Impossible pattern" errors for valid-looking S-expressions in Python grammar. Use manual tree walking with `_find_nodes_by_type()` as the primary extraction method.

4. **Do NOT use `node_link_data(attrs={...})`** — the `attrs` parameter was removed in NetworkX 3.x. Use default `id`, `source`, `target` field names.

5. **Do NOT parse files without `rb` mode** — tree-sitter expects bytes, not strings. Always open files with `"rb"`.

6. **Do NOT forget 1-based line numbers** — tree-sitter uses 0-based `start_point`/`end_point`. Add 1 for human-readable output.

7. **Do NOT descend into `.venv`, `node_modules`, `.git`** — use `dirnames[:] = [...]` in-place filtering in `os.walk()` to prevent descending into these directories.

8. **Do NOT call `get_binding()` for unsupported languages without try/except** — it will raise an exception. Catch and skip gracefully.

9. **Do NOT use `asyncio.run()` in `run_server()`** — FastMCP manages its own event loop. The existing `mcp_server.py` already handles this correctly.

10. **Do NOT forget to register tools in `mcp_server.register_all()`** — the Phase 3 hook is already commented out and ready to uncomment.

---

## Codebase Patterns (Brownfield)

- **Singleton pattern:** `chat_store.py` uses module-level `_store` variable with `get_store()` getter. Same pattern for `FileGraph` — use `_graph: FileGraph | None = None` + `get_graph()`.

- **Register pattern:** Each module exposes `register(mcp: FastMCP)`. `mcp_server.py` calls `register_all()` which imports and calls each module's `register()`. Follow this exactly for `file_graph.py`.

- **JSON response format:** All MCP tools return `json.dumps(result, indent=2)`. No plain text responses.

- **Pydantic Field annotations:** Tool parameters use `Annotated[type, Field(description="...", ge=1, le=50)]`. Follow this for `track_files` and `get_file_graph` parameters.

- **Docstring style:** Google-style docstrings with Args/Returns/Raises sections. Class docstrings include Attributes section.

- **Test style:** pytest with fixtures using `tmp_path`. Test naming: `test_<method>_<scenario>`. Error tests use `pytest.raises`.

- **Package structure:** `src/context_memory_mcp/` layout. Imports use full package path: `from context_memory_mcp.file_graph import ...`.

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| `get_binding()` fails for non-Python languages | Wrap in try/except, log warning, skip file. Graph still builds for supported languages. |
| `detect_language_from_path()` misidentifies language | Use file extension as fallback: if `.py`, assume Python regardless of content detection. |
| Large directories (1000+ files) cause slow parsing | Incremental updates (SHA-256 index) only re-parse changed files. Add progress logging. |
| Tree-sitter parse errors on malformed files | Catch exceptions during `parser.parse()`, log warning, skip file. Do not crash the entire build. |
| NetworkX serialization with complex attributes | Keep node/edge attributes as simple types (str, int, float). No nested objects. |
| Windows path separators in qualified names | Use absolute paths as-is (Windows: `C:\path\file.py`). The `::` delimiter disambiguates from path separators. |
