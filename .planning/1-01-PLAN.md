---
phase: 1
plan: 01
type: feature
wave: 1
depends_on: []
---

## Objective
Create project scaffold, dependencies, and a runnable FastMCP server with stdio transport that responds to a `ping` tool call. Success = `python -m context_memory_mcp` starts, responds to `--help`, and the ping tool returns `{status: "ok", version: "0.1.0", storage: "chromadb-ready"}`.

## Context
- Phase 1 of Context Memory MCP Server (personal weekend project)
- Uses `uv` for package management, `src/` layout with `context_memory_mcp/` package
- Official MCP SDK (`mcp` package, not standalone `fastmcp`)
- CLI subcommands: `start`, `stop`, `status`, `config` via stdlib argparse
- MCP transport: stdio only
- Placeholder modules follow code-review-graph style (signatures + docstrings)
- Research documented in `1-RESEARCH.md`, decisions in `1-CONTEXT.md`

## Tasks

### Task 1: Scaffold project layout with `pyproject.toml`
**Type:** auto  
**Dependencies:** none  
**Estimated effort:** 10 min

Create the project directory structure and `pyproject.toml`:

**Files to create:**
- `src/context_memory_mcp/__init__.py` — package init with `__version__ = "0.1.0"`
- `tests/` — empty directory (tests deferred to Phase 4)
- `pyproject.toml` — project config with uv_build backend

**File content — `pyproject.toml`:**
```toml
[project]
name = "context-memory-mcp"
version = "0.1.0"
description = "MCP server for persistent chat memory and file relationship tracking"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "chromadb>=0.4.0",
    "sentence-transformers>=2.2.0",
    "tree-sitter-language-pack>=0.1.0",
    "networkx>=3.0",
]

[project.scripts]
context-memory-mcp = "context_memory_mcp.cli:main"

[build-system]
requires = ["uv_build>=0.4.0,<5"]
build-backend = "uv_build"
```

**File content — `src/context_memory_mcp/__init__.py`:**
```python
"""Context Memory MCP Server — persistent chat history and file relationship tracking."""

__version__ = "0.1.0"
```

**Acceptance criteria:**
- [ ] `pyproject.toml` exists with correct project name, version, dependencies, and build system
- [ ] `src/context_memory_mcp/__init__.py` exists with `__version__ = "0.1.0"`
- [ ] `tests/` directory exists (can be empty)
- [ ] `uv sync` succeeds and creates `.venv` with all dependencies installed

---

### Task 2: Create CLI entry point (`__main__.py`)
**Type:** auto  
**Dependencies:** Task 1  
**Estimated effort:** 5 min

Create `src/context_memory_mcp/__main__.py` to enable `python -m context_memory_mcp` support.

**File content:**
```python
"""Entry point for `python -m context_memory_mcp`."""
import sys
from context_memory_mcp.cli import main

sys.exit(main())
```

**Acceptance criteria:**
- [ ] `__main__.py` exists with correct import and `sys.exit(main())` call
- [ ] `uv run python -m context_memory_mcp --help` runs without import errors (after Task 4 is also done)

---

### Task 3: Create CLI interface (`cli.py`)
**Type:** auto  
**Dependencies:** Task 1  
**Estimated effort:** 20 min

Create `src/context_memory_mcp/cli.py` with argparse subcommands: `start`, `stop`, `status`, `config`.

**Requirements:**
- Use `add_subparsers(dest="command")` for subcommand routing
- `start` — lazy import and call `run_server()` from `mcp_server`
- `stop` — print "not supported in stdio mode" (stdio runs in foreground)
- `status` — print version and "ready" status
- `config` — print default config info
- Return `int` exit codes for clean `sys.exit()` integration
- Accept `argv: list[str] | None = None` for testability

**Reference:** Full implementation template in `1-RESEARCH.md` §3 (CLI Argparse Pattern)

**Acceptance criteria:**
- [ ] `uv run python -m context_memory_mcp --help` shows all 4 subcommands
- [ ] `uv run python -m context_memory_mcp status` prints version and status
- [ ] `uv run python -m context_memory_mcp stop` prints not-supported message (exit 0)
- [ ] `uv run python -m context_memory_mcp config --show` prints default config
- [ ] No subcommand → prints help and exits with code 0
- [ ] Lazy import of `run_server` (no import at module level)

---

### Task 4: Create FastMCP server with `ping` tool
**Type:** auto  
**Dependencies:** Task 1 (dependencies installed)  
**Estimated effort:** 15 min

Create `src/context_memory_mcp/mcp_server.py` with:
- `FastMCP("context-memory-mcp")` instance named `mcp`
- `@mcp.tool(name="ping", description="...")` decorated async function
- Ping returns JSON: `{"status": "ok", "version": "0.1.0", "storage": "chromadb-ready"}`
- `run_server()` function calling `mcp.run(transport="stdio")`

**CRITICAL:** Do NOT wrap `mcp.run()` in `asyncio.run()` — FastMCP manages its own event loop.

**Reference:** Full implementation template in `1-RESEARCH.md` §1 (FastMCP Server Setup) and §5 (Directly Usable Code Snippets)

**Acceptance criteria:**
- [ ] `mcp_server.py` exists with `FastMCP` instance and `ping` tool
- [ ] `ping` tool is `async def` and returns a JSON string
- [ ] `run_server()` calls `mcp.run(transport="stdio")` directly (no `asyncio.run`)
- [ ] `uv run python -m context_memory_mcp start` starts the server (blocks on stdio)
- [ ] MCP client can call `ping` tool and receives `{"status": "ok", "version": "0.1.0", "storage": "chromadb-ready"}`

---

### Task 5: Create placeholder modules
**Type:** auto  
**Dependencies:** Task 1  
**Estimated effort:** 15 min

Create 5 placeholder modules with class/function signatures and docstrings (code-review-graph style):

**Files to create:**
- `src/context_memory_mcp/chat_store.py` — ChromaDB chat history storage
- `src/context_memory_mcp/file_graph.py` — File relationship graph
- `src/context_memory_mcp/parser.py` — Tree-sitter AST parser
- `src/context_memory_mcp/embeddings.py` — Local embedding wrapper
- `src/context_memory_mcp/context.py` — Token-efficient context retrieval

**Requirements:**
- Each file has a module-level docstring describing its purpose
- Each file has a class with `__init__` and key method signatures
- Method bodies use `...` (Ellipsis), NOT `raise NotImplementedError`
- Type hints on all signatures
- Docstrings on classes and methods describing behavior

**Reference:** Placeholder module pattern in `1-RESEARCH.md` §4 (code-review-graph style example for `chat_store.py`)

**Acceptance criteria:**
- [ ] All 5 placeholder files exist in `src/context_memory_mcp/`
- [ ] Each file has a module-level docstring
- [ ] Each file has at least one class with method signatures and docstrings
- [ ] No `NotImplementedError` — use `...` (Ellipsis) for method bodies
- [ ] `uv run python -c "import context_memory_mcp.chat_store"` succeeds (no syntax errors)
- [ ] `uv run python -c "import context_memory_mcp.file_graph"` succeeds
- [ ] `uv run python -c "import context_memory_mcp.parser"` succeeds
- [ ] `uv run python -c "import context_memory_mcp.embeddings"` succeeds
- [ ] `uv run python -c "import context_memory_mcp.context"` succeeds

---

### Task 6: Checkpoint — verify end-to-end Phase 1
**Type:** checkpoint  
**Dependencies:** Tasks 2, 3, 4, 5  
**Estimated effort:** 10 min

Run the full Phase 1 verification suite and await user approval before marking Phase 1 complete.

**Verification steps:**
1. `uv run python -m context_memory_mcp --help` — shows CLI help with all subcommands
2. `uv run python -m context_memory_mcp status` — prints `Context Memory MCP Server v0.1.0` and `Status: ready`
3. `uv run python -m context_memory_mcp start` — server starts and blocks on stdio (verify no startup errors)
4. Verify file tree matches the expected structure from `1-CONTEXT.md`

**Acceptance criteria:**
- [ ] All 4 CLI subcommands respond without errors
- [ ] Server starts without import errors or exceptions
- [ ] File tree matches: `src/context_memory_mcp/` with 9 files (`__init__.py`, `__main__.py`, `cli.py`, `mcp_server.py`, `chat_store.py`, `file_graph.py`, `parser.py`, `embeddings.py`, `context.py`)
- [ ] `uv sync` reports all dependencies resolved and installed
- [ ] **STOP — wait for user approval** before proceeding to Phase 2

---

## Verification
- [ ] `pyproject.toml` has correct project name, version, dependencies, and build system config
- [ ] `uv sync` completes without errors — all 5 dependencies installed
- [ ] `python -m context_memory_mcp --help` shows 4 subcommands (start, stop, status, config)
- [ ] `python -m context_memory_mcp status` prints version and ready status
- [ ] `python -m context_memory_mcp start` launches FastMCP server on stdio without errors
- [ ] Ping tool returns `{"status": "ok", "version": "0.1.0", "storage": "chromadb-ready"}`
- [ ] All 5 placeholder modules import without errors
- [ ] All changes committed with `[GSD-1-01-T{n}]` commit messages

## Expected Output
- Working project scaffold with `src/` layout
- `uv`-managed virtual environment with all dependencies
- Runnable CLI with 4 subcommands
- FastMCP server responding to `ping` tool over stdio
- 5 placeholder modules ready for Phase 2–4 implementation
- `.planning/1-01-SUMMARY.md` documenting execution results
