# Context Memory MCP Server

An MCP server that stores chat history in ChromaDB and tracks file changes using graph/tree structures. Built for personal use to save tokens by retrieving stored context instead of re-sending it with every request.

## Features

- 🗣️ **Chat History Storage** — Store and semantically search conversation history using ChromaDB vector embeddings
- 📁 **File Change Tracking** — Build and query file relationship graphs with NetworkX
- 🔍 **Token-Efficient Context** — Get compressed context optimized for LLM consumption (minimal/summary/full)
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

**Returns:** `["sess-abc123", "sess-def456", ...]` (sorted alphabetically)

---

#### `delete_session`
Delete all messages from a specific session.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `session_id` | `str` | Yes | The session to delete |

**Returns:** Number of messages deleted (int)

---

#### `prune_sessions`
Remove old sessions to control collection size.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `before_date` | `str | None` | `None` | Delete sessions with last_message before this ISO 8601 date |
| `max_sessions` | `int | None` | `None` | Keep only N most recent sessions |

**Example:**
```json
{
  "max_sessions": 5
}
```

**Returns:** `{"pruned": 3, "remaining": 5}`

---

### Context Retrieval

#### `get_context`
Get token-efficient context for a query. Combines recent chat history and metadata into a compressed window.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | — | Search query |
| `session_id` | `str | None` | `None` | Optional session filter |
| `detail_level` | `str` | `"summary"` | Output detail level: `"minimal"` (~100 tokens), `"summary"` (~300 tokens), `"full"` (raw JSON) |
| `active_files` | `list[str] | None` | `None` | Optional active file paths |

**Example:**
```json
{
  "query": "How does the file graph work?",
  "detail_level": "minimal",
  "active_files": ["file_graph.py", "parser.py"]
}
```

**Returns:**
```json
{
  "query": "How does the file graph work?",
  "content": "Query: How does the file graph work?\nActive files: 2",
  "token_count": 12,
  "detail_level": "minimal"
}
```

---

### File Graph

#### `track_files`
Build or update the file relationship graph for a directory. Parses all code files, extracts symbols (classes, functions, imports), and builds a NetworkX DiGraph with relationships.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `directory` | `str` | Yes | Path to the directory to scan |

**Example:**
```json
{
  "directory": "/path/to/project"
}
```

**Returns:**
```json
{
  "status": "ok",
  "file_count": 15,
  "node_count": 130,
  "edge_count": 60,
  "built_at": "2024-06-15T10:00:00+00:00"
}
```

---

#### `get_file_graph`
Get the file relationship subgraph for a specific file.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | `str` | Yes | Path to the file to query |

**Example:**
```json
{
  "file_path": "/path/to/project/src/chat_store.py"
}
```

**Returns:**
```json
{
  "file": "/abs/path/chat_store.py",
  "nodes": [...],
  "edges": [...],
  "dependencies": ["parser.py"],
  "dependents": ["mcp_server.py"],
  "impact_summary": {
    "direct_dependencies": 1,
    "direct_dependents": 1
  }
}
```

> **Note:** Run `track_files` first before using `get_file_graph`. If no graph data is available, an error message is returned.

---

## Architecture

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
│         │                 │          │  └───────────┬───────────┘│ │
│         │                 │          └──────────────┼────────────┘ │
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
└─────────────────────┘               └─────────────────────────────┘
```

### Data Flow

1. **Chat Storage:** Client → `store_chat` → ChromaDB (vector embeddings) → Session Index (JSON)
2. **Chat Query:** Client → `query_chat` → ChromaDB semantic search → Python date/role filtering → Results
3. **Context Retrieval:** Client → `get_context` → ContextBuilder → Compression → Formatted output
4. **File Tracking:** Client → `track_files` → ASTParser (tree-sitter) → FileGraph (NetworkX) → JSON
5. **File Query:** Client → `get_file_graph` → Graph traversal → Dependencies/dependents → Subgraph

## Configuration

### Environment

| Variable | Description | Default |
|----------|-------------|---------|
| ChromaDB path | `./data/chromadb` | Auto-created on first store |
| Session index | `./data/session_index.json` | Auto-created on first store |
| File graph | `./data/file_graph.json` | Auto-saved by `save()` |

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

A: The `SentenceTransformerEmbeddingFunction` downloads ~80MB of model weights (`all-MiniLM-L6-v2`) on first instantiation. This is a one-time cost. Subsequent runs are fast.

### Q: Can I use this with multiple projects?

A: Yes. Each project should have its own instance of the server with separate data directories. Use different `chroma_path` values per project to avoid collisions.

### Q: How do I back up my chat history?

A: Copy the `./data/` directory. It contains:
- `chromadb/` — ChromaDB SQLite database with all messages
- `session_index.json` — Session metadata cache
- `file_graph.json` — Persisted file relationship graph (if saved)

### Q: What languages does the file parser support?

A: The `ASTParser` uses tree-sitter and supports: Python, JavaScript, TypeScript, TSX, Go, Rust, Java, C, C++. Import matching is currently optimized for Python files.

### Q: How do I reduce the size of my ChromaDB collection?

A: Use `prune_sessions` with `max_sessions` or `before_date` to delete old sessions. The session index is automatically updated.

### Q: Why does `query_chat` sometimes return low-similarity results?

A: Semantic search always returns the most similar results within the specified session/filter. If only a few messages exist in the session, those will be returned even with low similarity scores. Use `date_from`/`date_to` filters to narrow the search window.

## Troubleshooting

### Model download fails or hangs

**Symptom:** `SentenceTransformerEmbeddingFunction` fails to initialize.

**Fix:**
1. Check your internet connection
2. Set `SENTENCE_TRANSFORMERS_HOME` to a writable directory
3. Try running with `HF_HUB_DISABLE_PROGRESS_BARS=1` to reduce output noise
4. The model will be cached after first download — subsequent runs are fast

### ChromaDB "database is locked" on Windows

**Symptom:** `sqlite3.OperationalError: database is locked`

**Fix:**
1. Ensure only one instance of the server is running
2. Call `store.close()` before process exit (handled automatically by the server)
3. On Windows, SQLite file locks can persist — restart your terminal if needed

### No graph data from `get_file_graph`

**Symptom:** Returns `{"error": "No graph data available. Run track_files first."}`

**Fix:** Run `track_files` with a valid directory path first. The graph is built from scratch on each `track_files` call.

### `tree-sitter` parser fails to initialize

**Symptom:** Warning logged: `Failed to initialize tree-sitter parser`

**Fix:**
1. Ensure `tree-sitter-language-pack` is installed: `pip install tree-sitter-language-pack`
2. The parser gracefully falls back to empty results — no crash
3. On some systems, `tree-sitter` requires a C compiler for native extensions

### Import matching returns fewer edges than expected

**Symptom:** `get_file_graph` shows fewer `IMPORTS_FROM` edges than expected.

**Explanation:** Import matching only creates edges when the imported module name matches a **known file** in the scanned directory. External packages (e.g., `import os`, `import numpy`) are not tracked as edges because they're not in the project's file set.

## Development

### Project Structure

```
memory/
├── src/
│   └── context_memory_mcp/
│       ├── __init__.py          # Package version
│       ├── __main__.py           # python -m entry point
│       ├── cli.py                # CLI interface (argparse)
│       ├── mcp_server.py         # FastMCP server + register_all()
│       ├── chat_store.py         # ChromaDB storage + session management
│       ├── context.py            # Token-efficient context windows
│       ├── file_graph.py         # NetworkX file relationship graph
│       └── parser.py             # tree-sitter AST parser + edge extraction
├── tests/
│   ├── test_chat_store.py        # ChatStore CRUD + pruning + index tests
│   ├── test_context.py           # Context compression + formatting tests
│   ├── test_file_graph.py        # FileGraph build + query + persistence tests
│   ├── test_parser.py            # ASTParser + edge extraction tests
│   └── test_integration.py       # End-to-end integration tests (all tools)
├── data/                         # Auto-created: chromadb, session index, graph
├── scripts/                      # Utility scripts
├── pyproject.toml                # Package metadata + dependencies
└── README.md                     # This file
```

### Running Tests

```bash
# Run all tests
py -m pytest tests/ -v

# Run specific test file
py -m pytest tests/test_integration.py -v

# Run with coverage
py -m pytest tests/ --cov=context_memory_mcp --cov-report=term-missing

# Run fast (skip slow tests)
py -m pytest tests/ -v -k "not performance"
```

**Current test count:** 191 tests passing.

### Code Style

- Type hints throughout (Python 3.11+ syntax)
- Docstrings for all public functions and classes
- `pytest` for testing, `tmp_path` fixture for isolation
- No `numpy`, no cloud APIs — local-first design

### Contributing

This is a personal weekend project. However, if you find it useful:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all 191+ tests pass
5. Submit a pull request

### License

Personal use. No formal license specified yet.

---

**Built with:** FastMCP, ChromaDB, SentenceTransformers, NetworkX, tree-sitter

**Inspired by:** code-review-graph architecture, spec-driven development (GSD)
