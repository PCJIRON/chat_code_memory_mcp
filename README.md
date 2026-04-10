# Context Memory MCP Server

An MCP server that stores chat history in ChromaDB and tracks file changes using graph/tree structures. Built for personal use to save tokens by retrieving stored context instead of re-sending it with every request.

## Features

- 🗣️ **Chat History Storage** — Store and semantically search conversation history using ChromaDB vector embeddings
- 📁 **File Change Tracking** — Build and query file relationship graphs with NetworkX
- 🔍 **Token-Efficient Context** — Get compressed context optimized for LLM consumption (minimal/summary/full)
- 🤖 **Automatic Mode** — Zero-touch auto-save, auto-retrieve, and auto-track (Phase 5)
- 🧠 **Hybrid Context System** — Semantic intent classification + unified ChromaDB + FileGraph dual-source retrieval (Phase 6)
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

The server provides **10 tools** across 3 domains:

### Core

#### `ping`
Check server status and readiness.

**Parameters:** None

**Returns:**
```json
{
  "status": "ok",
  "version": "0.6.0",
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

#### `query_file_changes`
Query file change history by semantic similarity with optional filters. Searches both chat history and file changes stored in unified ChromaDB.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | — | Natural language search query |
| `top_k` | `int` | `5` | Number of results to return (1–50) |
| `date_from` | `str | None` | `None` | ISO 8601 start date (e.g. `2024-01-01T00:00:00`) |
| `date_to` | `str | None` | `None` | ISO 8601 end date |
| `file_path` | `str | None` | `None` | Filter to specific file path |
| `change_type` | `str | None` | `None` | Filter by type: `"modified"`, `"created"`, `"deleted"` |

**Example:**
```json
{
  "query": "which files changed last week",
  "top_k": 5,
  "date_from": "2026-04-03T00:00:00",
  "date_to": "2026-04-10T23:59:59"
}
```

**Returns:**
```json
{
  "query": "which files changed last week",
  "total_found": 3,
  "results": [
    {
      "content": "modified src/chat_store.py: Added store_file_change...",
      "type": "file_change",
      "file_path": "src/chat_store.py",
      "change_type": "modified",
      "symbols": ["store_file_change", "query_file_changes"],
      "timestamp": "2026-04-08T14:30:00+00:00",
      "distance": 0.1234,
      "similarity": 0.8766
    }
  ]
}
```

> **Note:** File changes are automatically logged when `track_files` runs or when the file watcher detects changes. No manual setup needed.

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
Before each tool call, **~300 tokens of relevant context** are automatically queried from ChromaDB + FileGraph and injected into the response.

- **How it works:** `ContextInjector` uses `HybridContextBuilder` with semantic intent classification
- **Intent Classification:** Pre-computed sentence-transformers centroids classify query intent (chat/file/both)
- **Dual-Source Retrieval:** Queries ChromaDB (chat + file changes) + FileGraph based on detected intent
- **Token Budget:** ~300 tokens by default (configurable via `auto_context_tokens`, 60/40 chat/file split)
- **Dual Injection:** `[SYSTEM CONTEXT: ...]` format + source attribution for maximum LLM comprehension
- **Skipped Tools:** `ping`, `list_sessions`, `get_file_graph`, `delete_session` (non-query tools don't benefit)

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
│  │  1. _extract_query_from_arguments() → actual user query       │  │
│  │  2. IntentClassifier.classify() → chat/file/both intent       │  │
│  │  3. HybridContextBuilder.build() → ChromaDB + FileGraph       │  │
│  │  4. ContextInjector.inject() → [SYSTEM CONTEXT: ...] format   │  │
│  │  5. AutoSaveMiddleware.on_tool_call() → buffer                │  │
│  │  6. Original Tool Execution → Response                        │  │
│  │  7. AutoSaveMiddleware.on_tool_response() → flush to ChromaDB │  │
│  │  8. Return result (+ hybrid context if string)                │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │   Core Tools  │  │  Chat Memory │  │     File Graph Tools      │ │
│  │              │  │              │  │                           │ │
│  │  • ping      │  │  • store_chat│  │  • track_files            │ │
│  │              │  │  • query_chat│  │  • get_file_graph         │ │
│  │              │  │  • list_sess │  │  • query_file_changes     │ │
│  │              │  │  • delete_sess│ │                           │ │
│  │              │  │  • prune_sess │  │  ┌───────────────────────┐│ │
│  │              │  │  • get_context│  │  │    FileGraph (NX)    ││ │
│  └──────┬───────┘  └──────┬───────┘  │  │  • DiGraph            ││ │
│         │                 │          │  │  • SHA-256 tracking  ││ │
│         │                 │          │  │  • Incremental update ││ │
│         │                 │          │  │  • FileChange hooks  ││ │
│         │                 │          └───────────┬───────────┘│ │
│         │                 │                        │              │
│         │                 ▼                        │              │
│         │          ┌─────────────────────────┐    │              │
│         │          │  Hybrid Context System  │    │              │
│         │          │                         │    │              │
│         │          │  • IntentClassifier     │    │              │
│         │          │  • HybridContextBuilder │    │              │
│         │          │  • ContextInjector      │    │              │
│         │          │    (dual injection)     │    │              │
│         │          └─────────────────────────┘    │              │
│         │                                         │              │
└─────────┼─────────────────────────────────────────┼──────────────┘
          │                                         │
          ▼                                         ▼
┌─────────────────────┐               ┌─────────────────────────────┐
│   ChromaDB          │               │   File System               │
│   (Unified Storage) │               │   (code files parsed)       │
│                     │               │                             │
│  • Chat messages    │               │  • NetworkX DiGraph         │
│  • File changes     │               │  • ASTParser (tree-sitter)  │
│  • Semantic search  │               │  • JSON persistence         │
│  • Intent centroids │               │  • FileChange hooks         │
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

1. **Chat Storage:** Client → `store_chat` → ChromaDB (vector embeddings, `type="chat"`) → Session Index (JSON)
2. **Chat Query:** Client → `query_chat` → ChromaDB semantic search → Python date/role filtering → Results
3. **Hybrid Context Retrieval:** Tool call → IntentClassifier → HybridContextBuilder → ChromaDB + FileGraph → Token-optimized context
4. **File Tracking:** Client → `track_files` → ASTParser (tree-sitter) → FileGraph (NetworkX) → JSON + FileChangeLog → ChromaDB
5. **File Query:** Client → `get_file_graph` → Graph traversal → Dependencies/dependents → Subgraph
6. **File Change Query:** Client → `query_file_changes` → ChromaDB (`type="file_change"`) → Date/file/type filtering → Results
7. **Auto-Save:** Tool call/response → AutoSaveMiddleware → Buffer → ChromaDB (automatic)
8. **Auto-Retrieve:** Tool call → `_extract_query_from_arguments()` → IntentClassifier → HybridContextBuilder → `[SYSTEM CONTEXT: ...]` injection (automatic)
9. **Auto-Track:** File change → watchdog Observer → debounce → FileGraph.update_graph → FileChangeLog → ChromaDB (automatic)

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

**Test Count:** 276 tests (224 existing + 52 Phase 6)

## Project Structure

```
memory/
├── src/
│   └── context_memory_mcp/
│       ├── __init__.py              # Package version + config exports
│       ├── cli.py                   # CLI entry point
│       ├── mcp_server.py            # FastMCP server + auto wiring + hybrid context
│       ├── chat_store.py            # ChromaDB unified storage (chat + file changes)
│       ├── context.py               # HybridContextBuilder + intent classification
│       ├── intent_classifier.py     # Semantic query classifier (sentence-transformers)
│       ├── file_graph.py            # NetworkX file relationship graph + change hooks
│       ├── parser.py                # AST/tree-sitter symbol parser
│       ├── config.py                # AutoConfig dataclass (Phase 5)
│       ├── auto_save.py             # Auto-save middleware (Phase 5)
│       ├── auto_retrieve.py         # Hybrid context injector (Phase 6)
│       └── file_watcher.py          # Watchdog file watcher + change logging (Phase 6)
├── tests/                           # 276 pytest tests
├── data/                            # Runtime data
│   ├── chromadb/                    # ChromaDB unified storage (chat + file changes)
│   ├── config.json                  # Auto configuration (Phase 5)
│   ├── session_index.json           # Session index for O(1) listing
│   └── file_graph.json              # File graph persistence
├── scripts/                         # Utility scripts
└── pyproject.toml                   # Project metadata
```

## Phase 6: Hybrid Context System

### Semantic Intent Classification

The server automatically classifies user queries into intent categories using the existing `sentence-transformers` model:

- **Chat intent** — Queries about past conversations (e.g., "What did we discuss?", "Remember what I said")
- **File intent** — Queries about code changes and structure (e.g., "Which files changed?", "Import dependencies")
- **Both intent** — Ambiguous queries that may benefit from both sources

Intent classification uses pre-computed centroid embeddings at startup — zero new dependencies, ~10-50ms latency per query.

### Unified ChromaDB Storage

Both chat messages and file change history are stored in the same ChromaDB collection with `type` metadata:

```
ChromaDB Collection (chat_history)
├── Chat Messages (type="chat" or missing, role, content, timestamp, session_id)
└── File Changes (type="file_change", file_path, change_type, symbols, snippet, timestamp)
```

This enables unified semantic search across both data types while supporting filtered queries.

### Hybrid Context Builder

The `HybridContextBuilder` replaces the stub `ContextBuilder` and provides:

1. **Intent-based routing** — Uses `IntentClassifier` to determine which data sources to query
2. **ChromaDB dual-source retrieval** — Queries chat history and/or file changes based on intent
3. **FileGraph structural queries** — When file intent detected, extracts file paths from query and queries the dependency graph
4. **Token budget enforcement** — 60% chat / 40% file split, adjustable via configuration
5. **Graceful degradation** — Works without FileGraph or classifier (fallback to "both" intent)

### File Change History Tracking

File changes are automatically logged to ChromaDB at multiple points:

- **FileGraph updates** — When `update_graph()` processes changed files
- **FileWatcher callbacks** — When watchdog detects file modifications, creations, or deletions

Each file change document includes: file path, change type (modified/created/deleted), symbols added/removed, code snippet (truncated to 200 chars), and timestamp.

### Auto-Retrieve Fix (Phase 6)

**Critical bug fixed:** The auto-retrieve system was passing the tool *name* (e.g., `"query_chat"`) as the query instead of the actual user query from tool arguments. This has been fixed with `_extract_query_from_arguments()` which extracts the most relevant string from the arguments dictionary (priority: `query` > `conversation` > `search` > `text` > `content`).

### Dual Context Injection

Context is injected into tool responses using a dual format:

```
[SYSTEM CONTEXT: sources=chat_history, file_changes]
{retrieved context content}
[Sources: chat_history, file_changes]
```

This ensures the LLM sees context as a system-like instruction rather than just appended text.

### Example Queries by Intent

| Query | Detected Intent | Sources Queried |
|-------|----------------|-----------------|
| "What did we discuss about caching?" | `chat` | ChromaDB (chat only) |
| "Which files changed recently?" | `file` | ChromaDB (file changes) + FileGraph |
| "What did we say about the imports in chat_store.py?" | `both` | ChromaDB (both) + FileGraph |
| "Show me dependencies of file_graph.py" | `file` | ChromaDB (file changes) + FileGraph |

## License

Personal project — not for commercial use.
