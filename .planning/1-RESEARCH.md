# Phase 1 Research — Foundation

## Phase Goals
Create project scaffold, dependencies, and a runnable FastMCP server with stdio transport that responds to a ping tool. Deliver a working `python -m context_memory_mcp` entry point with CLI subcommands and all placeholder modules in place.

---

## Approaches Considered

### Approach 1: Official MCP SDK (`mcp` package with `FastMCP`)
**Description:** Use `mcp` PyPI package which includes `mcp.server.fastmcp.FastMCP` — the official high-level Python SDK from the Model Context Protocol project. Decorator-based tool registration with Pydantic Field for parameter schemas.
**Pros:** Official SDK, actively maintained, clean decorator API, stdio transport built-in, Pydantic validation out of the box
**Cons:** Occasional Windows stdio quirks (see Risks), requires async/await pattern
**Complexity:** Low
**Time Estimate:** 30 min for server + ping tool

### Approach 2: Standalone `fastmcp` package (PrefectHQ)
**Description:** The original `fastmcp` package by PrefectHQ, a separate higher-level wrapper.
**Pros:** Simpler API in some cases
**Cons:** Less actively maintained, has known Windows stdio issues (OSError WinError 10106), may conflict with official `mcp` package
**Complexity:** Low-Medium
**Time Estimate:** 30-45 min

### Approach 3: Raw MCP protocol (manual JSON-RPC over stdio)
**Description:** Implement the MCP JSON-RPC protocol manually using `sys.stdin`/`sys.stdout` without any framework.
**Pros:** Full control, no framework dependencies, minimal attack surface
**Cons:** Reinvent tool registration, JSON-RPC framing, error handling, content-type negotiation — significant boilerplate
**Complexity:** High
**Time Estimate:** 2-3 hours

### Approach 4: CLI framework — Click vs argparse
**Description:** Use Click library for CLI subcommands instead of stdlib argparse.
**Pros:** Cleaner decorator-based CLI definition, better help output
**Cons:** Additional dependency, overkill for 4 simple subcommands, argparse is built-in and sufficient
**Complexity:** Low (Click) / Low (argparse)
**Time Estimate:** Same either way (~15 min)

---

## Recommended Approach

**Selected: Approach 1 (Official MCP SDK `mcp` package) + stdlib argparse**

**Why:**
- `mcp.server.fastmcp.FastMCP` is the official Python SDK, used by the broader MCP ecosystem
- Clean `@mcp.tool()` decorator with Pydantic `Field` for parameter descriptions
- `mcp.run(transport="stdio")` handles all JSON-RPC framing automatically
- argparse is built-in, no extra dependency for 4 subcommands
- Proven pattern from multiple working MCP servers

---

## Implementation Notes

### 1. FastMCP Server Setup

```python
# src/context_memory_mcp/mcp_server.py
import asyncio
import json
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from context_memory_mcp import __version__

# Server instance — name appears in MCP client tool listings
mcp = FastMCP("context-memory-mcp")


@mcp.tool(
    name="ping",
    description="Check if the server is running and return status information."
)
async def ping() -> str:
    """Ping the server to verify it is running."""
    status = {
        "status": "ok",
        "version": __version__,
        "storage": "chromadb-ready",
    }
    return json.dumps(status)


def run_server():
    """Start the FastMCP server with stdio transport."""
    mcp.run(transport="stdio")
```

**Key patterns:**
- `FastMCP("name")` — creates server instance; name is shown to MCP clients
- `@mcp.tool(name="...", description="...")` — registers function as an MCP tool
- Tool functions must be `async def` (FastMCP runs in async event loop)
- Type hints on parameters → Pydantic schema → MCP tool input schema
- Return type should be `str` — the string is the tool result
- `mcp.run(transport="stdio")` — starts the JSON-RPC server on stdin/stdout
- No need for `asyncio.run()` — `mcp.run()` manages its own event loop

### 2. pyproject.toml Template (src Layout with uv)

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

**Why this configuration:**
- `[project.scripts]` creates a CLI entry point installable via `uv sync`
- `uv_build` is the recommended build backend for uv-managed projects
- `requires-python = ">=3.11"` — ensures modern Python with better async support
- Dependencies pinned to minimum versions; uv handles exact resolution in `uv.lock`
- The `context-memory-mcp` script name matches the project for discoverability

**For `python -m` support:**
Create `src/context_memory_mcp/__main__.py`:
```python
"""Entry point for `python -m context_memory_mcp`."""
from context_memory_mcp.cli import main

if __name__ == "__main__":
    main()
```

### 3. CLI Argparse Pattern for Subcommands

```python
# src/context_memory_mcp/cli.py
"""CLI interface for the Context Memory MCP server."""
import argparse
import sys

from context_memory_mcp import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="context-memory-mcp",
        description="Context Memory MCP Server — persistent chat history and file tracking",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # start — launch the MCP server
    subparsers.add_parser("start", help="Start the MCP server (stdio mode)")

    # stop — stop a running server (if running as daemon)
    subparsers.add_parser("stop", help="Stop the MCP server")

    # status — check server status
    subparsers.add_parser("status", help="Show server status")

    # config — show or modify configuration
    config_parser = subparsers.add_parser("config", help="Show or modify configuration")
    config_parser.add_argument("--show", action="store_true", help="Show current configuration")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point. Returns exit code."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "start":
        from context_memory_mcp.mcp_server import run_server
        run_server()
        return 0

    if args.command == "stop":
        print("Server stop not supported (stdio mode runs in foreground)")
        return 0

    if args.command == "status":
        print(f"Context Memory MCP Server v{__version__}")
        print("Status: ready (stdio mode)")
        return 0

    if args.command == "config":
        print("Configuration: default (no config file)")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Pattern notes:**
- `add_subparsers(dest="command")` — makes the subcommand name available as `args.command`
- Each subcommand is a simple `add_parser()` call — no extra args needed for start/stop/status
- `config` subcommand shows how to add options to a subcommand
- Lazy import of `run_server` inside the handler — avoids importing MCP server during `--help`
- Returns `int` exit code for clean `sys.exit()` integration
- `argv: list[str] | None = None` — allows unit testing by passing custom args

### 4. `__init__.py` — Package Version

```python
# src/context_memory_mcp/__init__.py
"""Context Memory MCP Server — persistent chat history and file relationship tracking."""

__version__ = "0.1.0"
```

### 5. Placeholder Module Pattern (code-review-graph Style)

```python
# src/context_memory_mcp/chat_store.py
"""ChromaDB-backed chat history storage with semantic search.

Stores conversation messages as vectors for semantic retrieval.
Each message is embedded using local sentence-transformers and
stored in ChromaDB with metadata (role, timestamp, conversation_id).
"""


class ChatStore:
    """Persistent chat history storage with vector similarity search.

    Uses ChromaDB for embedding-based retrieval of stored messages.
    Supports batch ingestion, semantic queries, and metadata filtering.
    """

    def __init__(self, persist_directory: str = ".chroma"):
        """Initialize ChromaDB collection and embedding function."""
        ...

    async def store_message(
        self, content: str, role: str, conversation_id: str | None = None
    ) -> str:
        """Embed and store a single chat message with metadata."""
        ...

    async def batch_store_messages(
        self, messages: list[dict[str, str]], conversation_id: str | None = None
    ) -> int:
        """Embed and store multiple messages in one batch.

        Returns the number of messages stored.
        """
        ...

    async def query_messages(
        self, query: str, top_k: int = 5, role: str | None = None,
        date_from: str | None = None, date_to: str | None = None,
    ) -> list[dict]:
        """Retrieve messages by semantic similarity with optional filters.

        Results include content, role, timestamp, and similarity score.
        """
        ...
```

---

## Windows-Specific Considerations

### Risk W5: FastMCP stdio on Windows
**Issue:** Some users report `OSError: [WinError 10106]` when using asyncio with stdio transport on Windows. This is related to Python's `asyncio.windows_events` importing `_overlapped`.
**Mitigation:**
- The server-side `mcp.run(transport="stdio")` does **not** typically trigger this issue — it occurs primarily in **client-side** stdio connections
- If encountered, try `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` before `mcp.run()`
- For Phase 1, test with the simple ping tool first to validate stdio works
- The `mcp` package (official SDK) is more actively maintained and has fewer Windows issues than the standalone `fastmcp` package

### Risk W6: uv on Windows
**Issue:** uv works well on Windows but requires proper Python discovery.
**Mitigation:**
- Ensure Python 3.11+ is installed and on PATH
- `uv sync` will automatically create `.venv` and install dependencies
- Run commands with `uv run python -m context_memory_mcp start` to use the venv
- Windows path length limits (260 chars) may affect ChromaDB file paths — use short project directory names

### Risk W7: tree-sitter-language-pack compilation
**Issue:** This package may require a C compiler on Windows (Phase 3).
**Mitigation:**
- Pre-built wheels are available for Windows on most versions
- If compilation fails, `uv pip install tree-sitter-language-pack --no-build-isolation` may help
- Defer to Phase 3 — not needed for Phase 1

---

## Libraries/Tools

| Library | Version | Why |
|---------|---------|-----|
| `mcp` | >=1.0.0 | Official MCP Python SDK, includes FastMCP — clean decorator API, stdio transport |
| `chromadb` | >=0.4.0 | Local vector database — persistent storage, no cloud dependency |
| `sentence-transformers` | >=2.2.0 | Local embeddings — privacy-focused, no API costs |
| `tree-sitter-language-pack` | >=0.1.0 | Multi-language AST parsing — file relationship extraction |
| `networkx` | >=3.0 | Graph data structures — file dependency tracking |
| `uv_build` | >=0.4.0 | Fast build backend for uv-managed projects |

---

## File Structure (Implementation Blueprint)

```
context-memory-mcp/
├── .venv/                          # Created by uv sync
├── src/
│   └── context_memory_mcp/
│       ├── __init__.py             # __version__ = "0.1.0"
│       ├── __main__.py             # python -m entry → cli.main()
│       ├── cli.py                  # argparse: start, stop, status, config
│       ├── mcp_server.py           # FastMCP stdio server + ping tool
│       ├── chat_store.py           # Placeholder: ChromaDB storage (Phase 2)
│       ├── file_graph.py           # Placeholder: File graph (Phase 3)
│       ├── parser.py               # Placeholder: Tree-sitter parser (Phase 3)
│       ├── embeddings.py           # Placeholder: Embedding wrapper (Phase 2)
│       └── context.py              # Placeholder: Context retrieval (Phase 4)
├── tests/                          # Empty directory for Phase 4
├── pyproject.toml                  # Package config + dependencies
├── uv.lock                         # Generated by uv sync
└── README.md                       # Phase 4
```

---

## Pitfalls to Avoid

1. **Don't use `asyncio.run(mcp.run())`** — FastMCP's `mcp.run()` manages its own event loop. Calling `asyncio.run()` around it can cause nested event loop errors.

2. **Don't import MCP server module in CLI during `--help`** — Lazy import `run_server` inside the `start` command handler. Otherwise, `python -m context_memory_mcp --help` will fail if MCP dependencies aren't fully installed yet.

3. **Don't forget `pydantic.Field` for tool parameters** — Without `Field(description="...")`, the MCP client won't see parameter descriptions, making tools harder for LLMs to use correctly.

4. **Don't use `@mcp.tool()` without `name` parameter** — The function name becomes the tool name. Always specify `name="snake_case_name"` explicitly for consistency.

5. **Don't mix `mcp` and `fastmcp` packages** — They are different packages. Use `from mcp.server.fastmcp import FastMCP` (official SDK), not `from fastmcp import FastMCP` (standalone).

6. **Don't skip `requires-python` in pyproject.toml** — uv needs this to select the correct Python version. Set to `>=3.11` minimum.

7. **Don't use `uv run` without `uv sync` first** — The virtual environment must be created before running commands through it.

---

## Directly Usable Code Snippets

### Task 1.1: pyproject.toml
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

### Task 1.3: `__main__.py`
```python
"""Entry point for `python -m context_memory_mcp`."""
import sys
from context_memory_mcp.cli import main

sys.exit(main())
```

### Task 1.5: `mcp_server.py` (ping tool only)
```python
"""FastMCP server with stdio transport."""
import json
from mcp.server.fastmcp import FastMCP
from context_memory_mcp import __version__

mcp = FastMCP("context-memory-mcp")


@mcp.tool(
    name="ping",
    description="Check if the server is running and return status information.",
)
async def ping() -> str:
    """Ping the server to verify it is running."""
    return json.dumps({
        "status": "ok",
        "version": __version__,
        "storage": "chromadb-ready",
    })


def run_server() -> None:
    """Start the FastMCP server with stdio transport."""
    mcp.run(transport="stdio")
```

### Manual Testing Commands (Phase 1)
```bash
# 1. Initialize project (if not done)
uv init --package --name context-memory-mcp

# 2. Install dependencies
uv sync

# 3. Verify CLI
uv run python -m context_memory_mcp --help
uv run python -m context_memory_mcp start --help  # (if start has sub-args)

# 4. Start server (stdio blocks — test with MCP client)
uv run python -m context_memory_mcp start

# 5. Quick status check (non-blocking)
uv run python -m context_memory_mcp status
```
