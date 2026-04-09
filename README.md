# Context Memory MCP Server

An MCP server that stores chat history in ChromaDB and tracks file changes using graph/tree structures. Built for personal use to save tokens by retrieving stored context instead of re-sending it with every request.

## Features

- 🗣️ **Chat History Storage** — Store and semantically search conversation history using ChromaDB vector embeddings
- 📁 **File Change Tracking** — Build and query file relationship graphs with NetworkX
- 🔍 **Token-Efficient Context** — Get compressed context optimized for LLM consumption (minimal/summary/full)
- 🤖 **Automatic Mode** — Zero-touch auto-save, auto-retrieve, and auto-track (Phase 5)
- 🏠 **Local-First** — All data stored locally, no cloud APIs, no external dependencies beyond pip packages
- 🔌 **MCP Protocol** — Stdio-based transport compatible with any MCP client

## Installation

### Prerequisites

- **Python 3.11+** (tested with Python 3.13.7)
- **pip** or **uv** for package management

### Setup

```bash
# Clone or navigate to the project
cd memory

# Option A: Using pip (recommended)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
pip install -e .

# Option B: Using uv
uv sync
```

> **Note:** On first run, the `SentenceTransformerEmbeddingFunction` will download ~80MB of model weights (~25s). This is expected — do not interrupt.

## Quick Start

```bash
# Activate your virtual environment first
# Then start the MCP server (stdio transport)
python -m context_memory_mcp

# View CLI help
python -m context_memory_mcp --help

# Check version
python -m context_memory_mcp status
```

The server runs on stdio transport by default. Connect it to any MCP-compatible client (Claude Desktop, Cursor, etc.) by configuring the command:

```json
{
  "mcpServers": {
    "context-memory": {
      "command": "python",
      "args": ["-m", "context_memory_mcp"],
      "cwd": "/path/to/memory"
    }
  }
}
```

## MCP Tools

The server provides **9 tools** across 3 domains:

### Core

#### `ping`
Check server status and readiness.

**Parameters:** None

**Returns:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "storage": "chromadb-ready"
}
```

---

### Chat Memory

#### `store_chat`
Store a batch of chat messages in conversation history.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `messages` | `list[dict]` | Yes | List of `{role: "user"|"assistant"|"system", content: str}` objects |
| `session_id` | `str | None` | No | Session UUID. Auto-generated if omitted |

**Example:**
```json
{
  "messages": [
    {"role": "user", "content": "What is ChromaDB?"},
    {"role": "assistant", "content": "ChromaDB is an open-source vector database..."}
  ],
  "session_id": "sess-abc123"
}
```

**Returns:** `{"stored": 2, "session_id": "sess-abc123"}`

---

#### `query_chat`
Search chat history by semantic similarity with optional filters.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | — | Natural language search query |
| `top_k` | `int` | `5` | Number of results to return (1–50) |
| `session_id` | `str | None` | `None` | Filter to specific session |
| `conversation_id` | `str | None` | `None` | Alias for session_id (takes precedence) |
| `date_from` | `str | None` | `None` | ISO 8601 start date (e.g. `2024-01-01T00:00:00`) |
| `date_to` | `str | None` | `None` | ISO 8601 end date |
| `role` | `str | None` | `None` | Filter by role: `"user"`, `"assistant"`, `"system"` |

**Example:**
```json
{
  "query": "vector database",
  "top_k": 3,
  "session_id": "sess-abc123",
  "role": "assistant"
}
```

**Returns:**
```json
{
  "query": "vector database",
  "total_found": 2,
  "results": [
    {
      "content": "ChromaDB is an open-source vector database...",
      "role": "assistant",
      "timestamp": "2024-06-15T10:00:00+00:00",
      "session_id": "sess-abc123",
      "distance": 0.1234,
      "similarity": 0.8766
    }
  ]
}
```

---

#### `list_sessions`
List all available conversation session IDs.

**Parameters:** None

**Returns:** Sorted list of session IDs.

---

#### `delete_session`
Delete all messages from a specific session.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | `str` | Yes | Session UUID to delete |

**Returns:** Number of messages deleted.

---

#### `prune_sessions`
Remove old sessions to control collection size.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `before_date` | `str | None` | `None` | Delete sessions with last_message before this ISO 8601 date |
| `max_sessions` | `int | None` | `None` | Keep only N most recent sessions |

**Returns:** `{"pruned": N, "remaining": M}`

---

### File Graph

#### `track_files`
Build or update the file relationship graph for a directory.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `directory` | `str` | Yes | Path to the directory to scan |

**Returns:** JSON with status, file_count, node_count, edge_count.

---

#### `get_file_graph`
Get the file relationship subgraph for a specific file.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | `str` | Yes | Path to the file to query |

**Returns:** JSON with nodes, edges, dependencies, dependents.

> **Note:** Run `track_files` first before using `get_file_graph`. If no graph data is available, an error message is returned.

---

### Context Retrieval

#### `get_context`
Get token-efficient context for a query.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | Yes | Search query |
| `session_id` | `str | None` | `None` | Optional session filter |
| `detail_level` | `str` | `"summary"` | `minimal`, `summary`, or `full` |
| `active_files` | `list[str] | None` | `None` | Optional active file paths |

**Returns:** JSON with query, content, token_count, detail_level.

---

## Automatic Mode (Phase 5)

Phase 5 introduces **fully automatic behavior** — no manual tool calls needed for save, track, or retrieve. Every conversation is auto-saved, every file change is auto-detected, and every request is auto-enriched with stored context.

### Auto-Save
Every MCP tool call and response is **automatically captured and saved** to ChromaDB. No need to call `store_chat` manually.

- **How it works:** Server-side interception via monkey-patched `mcp.call_tool`
- **Trigger:** On tool response (after any MCP tool executes)
- **Buffering:** Tool call + response are buffered together, flushed on response
- **Session:** Auto-generated UUID, isolated from manual `store_chat` sessions
- **Truncation:** Large results (>500 chars) are truncated with "..."

### Auto-Retrieve
Before each tool call, **~300 tokens of relevant context** are automatically queried from ChromaDB and appended to the response.

- **How it works:** `ContextInjector` queries ChromaDB using `format_with_detail(level="summary")`
- **Token Budget:** ~300 tokens by default (configurable via `auto_context_tokens`)
- **Skipped Tools:** `ping`, `list_sessions`, `get_file_graph`, `delete_session` (non-query tools don't benefit)
- **Marker:** Context is clearly marked with `[Auto-Context]` header

### Auto-Track
A **background file watcher** monitors your code directories and automatically updates the file graph when files change.

- **How it works:** `watchdog` Observer runs in a separate OS thread (daemon)
- **Debounce:** 0.5s debounce handles OneDrive delayed/duplicate events
- **Ignored Dirs:** `.git`, `__pycache__`, `.venv`, `node_modules`, `data`
- **Clean Shutdown:** Observer stopped and joined on server exit

### Configuration

All automatic features are controlled by `./data/config.json`:

```json
{
  "auto_save": true,
  "auto_retrieve": true,
  "auto_track": true,
  "auto_context_tokens": 300,
  "watch_dirs": ["./src"],
  "watch_ignore_dirs": [".git", "__pycache__", ".venv", "node_modules", "data"],
  "flush_interval_seconds": 30
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `auto_save` | `bool` | `true` | Enable automatic tool call/response saving |
| `auto_retrieve` | `bool` | `true` | Enable automatic context injection |
| `auto_track` | `bool` | `true` | Enable background file watching |
| `auto_context_tokens` | `int` | `300` | Token budget for auto-injected context (clamped 50–2000) |
| `watch_dirs` | `list[str]` | `["./src"]` | Directories to monitor for file changes |
| `watch_ignore_dirs` | `list[str]` | See above | Directory names to skip during watching |
| `flush_interval_seconds` | `int` | `30` | Buffer flush interval (min 5s) |

### Toggling Features

To disable a feature, set it to `false` in `./data/config.json`:

```json
{
  "auto_save": false,
  "auto_retrieve": true,
  "auto_track": false
}
```

> **No Breaking Changes:** All features are opt-in via config. Default: all enabled. Manual tool calls (`store_chat`, `query_chat`, `track_files`) continue to work normally.

## Architecture

### With Automatic Mode

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MCP Client                                   │
│                   (Claude Desktop, Cursor, etc.)                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ stdio (MCP Protocol)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     MCP Server (FastMCP)                            │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              _intercepted_call_tool (monkey-patched)          │  │
│  │                                                               │  │
│  │  1. ContextInjector.inject() → ~300 tokens appended           │  │
│  │  2. AutoSaveMiddleware.on_tool_call() → buffer                │  │
│  │  3. Original Tool Execution → Response                        │  │
│  │  4. AutoSaveMiddleware.on_tool_response() → flush to ChromaDB │  │
│  │  5. Return result (+ context if string)                       │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │   Core Tools  │  │  Chat Memory │  │     File Graph Tools      │ │
│  │              │  │              │  │                           │ │
│  │  • ping      │  │  • store_chat│  │  • track_files            │ │
│  │              │  │  • query_chat│  │  • get_file_graph         │ │
│  │              │  │  • list_sess │  │                           │ │
│  │              │  │  • delete_sess│ │  ┌───────────────────────┐│ │
│  │              │  │  • prune_sess │  │  │    FileGraph (NX)    ││ │
│  │              │  │  • get_context│  │  │  • DiGraph            ││ │
│  └──────┬───────┘  └──────┬───────┘  │  │  • SHA-256 tracking  ││ │
│         │                 │          │  │  • Incremental update ││ │
│         │                 │          └───────────┬───────────┘│ │
│         │                 │                        │              │
│         │                 ▼                        │              │
│         │          ┌──────────────┐               │              │
│         │          │  Context System│               │              │
│         │          │              │               │              │
│         │          │  • ContextBuilder              │              │
│         │          │  • get_minimal_context         │              │
│         │          │  • format_with_detail          │              │
│         │          │    (minimal/summary/full)      │              │
│         │          └──────────────┘               │              │
│         │                                         │              │
└─────────┼─────────────────────────────────────────┼──────────────┘
          │                                         │
          ▼                                         ▼
┌─────────────────────┐               ┌─────────────────────────────┐
│   ChromaDB          │               │   File System               │
│   (Vector Storage)  │               │   (code files parsed)       │
│                     │               │                             │
│  • Chat messages    │               │  • NetworkX DiGraph         │
│  • Semantic search  │               │  • ASTParser (tree-sitter)  │
│  • Session index    │               │  • JSON persistence         │
│  • Auto-save buffer │               │                             │
└─────────────────────┘               └──────────────┬──────────────┘
                                                     │
                                          ┌──────────▼──────────────┐
                                          │   FileWatcher (thread)  │
                                          │  • watchdog Observer    │
                                          │  • 0.5s debounce        │
                                          │  • Auto-track handler   │
                                          └─────────────────────────┘
```

### Data Flow

1. **Chat Storage:** Client → `store_chat` → ChromaDB (vector embeddings) → Session Index (JSON)
2. **Chat Query:** Client → `query_chat` → ChromaDB semantic search → Python date/role filtering → Results
3. **Context Retrieval:** Client → `get_context` → ContextBuilder → Compression → Formatted output
4. **File Tracking:** Client → `track_files` → ASTParser (tree-sitter) → FileGraph (NetworkX) → JSON
5. **File Query:** Client → `get_file_graph` → Graph traversal → Dependencies/dependents → Subgraph
6. **Auto-Save:** Tool call/response → AutoSaveMiddleware → Buffer → ChromaDB (automatic)
7. **Auto-Retrieve:** Tool call → ContextInjector → ~300 tokens appended → Response (automatic)
8. **Auto-Track:** File change → watchdog Observer → debounce → FileGraph.update_graph (automatic)

## Configuration

### Environment

| Variable | Description | Default |
|----------|-------------|---------|
| ChromaDB path | `./data/chromadb` | Auto-created on first store |
| Session index | `./data/session_index.json` | Auto-created on first store |
| File graph | `./data/file_graph.json` | Auto-saved by `save()` |
| Auto config | `./data/config.json` | Auto-created with defaults |

### Token Estimation

Context compression uses a **4 chars/token heuristic** for fast estimation. This is approximate, not exact, but sufficient for MVP purposes.

### Detail Levels

| Level | Target Tokens | Use Case |
|-------|---------------|----------|
| `minimal` | ~100 | Quick context for LLM prompts |
| `summary` | ~300 | Detailed review with match highlights |
| `full` | Raw JSON | Complete data for debugging |

## FAQ

### Q: Why does the first run take ~25 seconds?

The `SentenceTransformerEmbeddingFunction` downloads ~80MB of model weights on first instantiation. This is a one-time cost — subsequent runs are fast.

### Q: Can I disable automatic features?

Yes. Set `auto_save`, `auto_retrieve`, or `auto_track` to `false` in `./data/config.json`. All features are independent.

### Q: How do I adjust the context token budget?

Change `auto_context_tokens` in `./data/config.json`. Valid range: 50–2000 (clamped automatically).

### Q: Why is my file watcher not detecting changes on OneDrive?

OneDrive produces delayed and duplicate file events. The built-in 0.5s debounce handles this. If you still see issues, increase `flush_interval_seconds`.

### Q: Can I watch multiple directories?

Yes. Add paths to `watch_dirs` in `./data/config.json`:
```json
{
  "watch_dirs": ["./src", "./tests", "./scripts"]
}
```

## Troubleshooting

### Windows DLL Errors

On Windows, you may see DLL loading errors from `torch`. This is a known issue with the sentence-transformers dependency. The server still functions correctly — these are warnings, not fatal errors.

### ChromaDB Lock Issues

If you see "database is locked" errors on Windows, ensure no other process is holding a lock on `./data/chromadb`. You may need to close the previous server instance or delete the lock file.

### File Watcher Not Starting

If you see "Watch directory does not exist" warnings, ensure the paths in `watch_dirs` exist. Non-existent directories are skipped gracefully.

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_auto_save.py -v

# Run with coverage
python -m pytest tests/ --cov=context_memory_mcp
```

**Test Count:** 224 tests (191 existing + 33 Phase 5)

## Project Structure

```
memory/
├── src/
│   └── context_memory_mcp/
│       ├── __init__.py           # Package version + config exports
│       ├── cli.py                # CLI entry point
│       ├── mcp_server.py         # FastMCP server + auto wiring
│       ├── chat_store.py         # ChromaDB chat history storage
│       ├── context.py            # Token-efficient context retrieval
│       ├── file_graph.py         # NetworkX file relationship graph
│       ├── parser.py             # AST/tree-sitter symbol parser
│       ├── config.py             # AutoConfig dataclass (Phase 5)
│       ├── auto_save.py          # Auto-save middleware (Phase 5)
│       ├── auto_retrieve.py      # Context injector (Phase 5)
│       └── file_watcher.py       # Watchdog file watcher (Phase 5)
├── tests/                        # 224 pytest tests
├── data/                         # Runtime data
│   ├── chromadb/                 # ChromaDB vector storage
│   ├── config.json               # Auto configuration (Phase 5)
│   ├── session_index.json        # Session index for O(1) listing
│   └── file_graph.json           # File graph persistence
├── scripts/                      # Utility scripts
└── pyproject.toml                # Project metadata
```

## License

Personal project — not for commercial use.
