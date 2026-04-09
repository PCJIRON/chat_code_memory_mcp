# Phase 5 Context — Auto Save, Track & Retrieve

## Phase Goal
Make the MCP server **fully automatic** — no manual tool calls needed for save, track, or retrieve. Every conversation auto-saved, every file change auto-detected, every request auto-enriched with stored context.

---

## Decisions

### Decision 1: Auto-Save Strategy — Server-Side Interception
- **Decision:** Intercept every tool call/response at the server level and automatically save to ChromaDB
- **Rationale:** Server-side approach means LLM doesn't need to explicitly call `store_chat` — every tool interaction is automatically captured. Works with any MCP client.
- **Alternatives considered:** Client-side wrapper (LLM must use it), FastMCP lifecycle hooks, custom MCP transport
- **Trade-offs:** Server interception is transparent to LLM but requires wrapping the tool execution flow. FastMCP doesn't have native middleware — we'll implement via tool response wrapping.

### Decision 2: Auto-Retrieve Strategy — Context Injection
- **Decision:** Implement `ContextInjector` that automatically queries ChromaDB before each tool call and appends ~300 tokens of relevant context
- **Rationale:** LLM gets enriched context automatically — doesn't need to call `get_context`. Every response is informed by stored history.
- **Alternatives considered:** LLM calls `get_context` explicitly, pre-fetch context on server start
- **Trade-offs:** Adds latency to every tool call (ChromaDB query), but ensures context is always fresh and relevant.

### Decision 3: Auto-Track Strategy — Background File Watcher
- **Decision:** Use `watchdog` library to monitor file system changes in background thread, auto-trigger `track_files` on modification
- **Rationale:** True zero-touch file tracking — no LLM call needed. Detects changes in real-time.
- **Alternatives considered:** Polling-based detection, LLM-triggered `track_files`
- **Trade-offs:** `watchdog` needs installation (`pip install watchdog`). Background thread adds memory overhead. Can be configured per directory.

### Decision 4: Auto-Save Trigger Points
- **Decision:** Auto-save on tool response — after any MCP tool executes, capture the interaction and save to ChromaDB
- **Rationale:** Tool response trigger captures LLM interactions precisely. No periodic flush needed — save happens exactly when interaction occurs.
- **Alternatives considered:** Save every N seconds only, save on server shutdown only
- **Trade-offs:** Tool response trigger is more precise — captures exactly when interaction happens.

### Decision 5: Auto-Retrieve Context Budget
- **Decision:** Auto-retrieve ~300 tokens (summary level) before each tool call — enough context without overwhelming
- **Rationale:** 300 tokens provides meaningful history without eating into the LLM's context window. Can be configured via `auto_context_tokens` setting.
- **Alternatives considered:** ~100 tokens (minimal), ~500 tokens (full recent history)
- **Trade-offs:** 300 tokens balances relevance vs. context budget. Adjustable per user preference.

### Decision 6: Configuration File
- **Decision:** Add `./data/config.json` for auto-settings:
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
- **Rationale:** User can toggle features on/off, configure watch directories, adjust context budget.
- **Alternatives considered:** Hardcoded defaults, environment variables only
- **Trade-offs:** JSON file is human-editable, version-controllable, and easy to modify.

---

## Architecture

### Auto-Save Flow
```
User ──→ LLM ──→ MCP Tool Call ──→ AutoSaveMiddleware.intercept()
                                            │
                                            ├── Execute tool
                                            │
                                            ├── Capture: (role, content, timestamp)
                                            │
                                            ├── Save to ChromaDB
                                            │
                                            └── Return tool response
```

### Auto-Retrieve Flow
```
LLM receives request
      │
      ├── ContextInjector.retrieve(query, top_k=5, session_id=current)
      │
      ├── Append context to prompt: "Recent context: ..."
      │
      └── LLM responds with informed context
```

### Auto-Track Flow
```
watchdog Observer Thread
      │
      ├── File modified: src/file.py
      │
      ├── Auto-trigger: track_files("./src")
      │
      └── Graph updated → ./data/file_graph.json saved
```

---

## Implementation Scope

| Component | File | Description |
|-----------|------|-------------|
| `ConfigManager` | `src/context_memory_mcp/config.py` | Loads/saves `./data/config.json` |
| `AutoSaveMiddleware` | `src/context_memory_mcp/auto_save.py` | Intercepts tool calls, auto-saves conversations |
| `ContextInjector` | `src/context_memory_mcp/auto_retrieve.py` | Auto-queries ChromaDB, appends context |
| `FileWatcher` | `src/context_memory_mcp/file_watcher.py` | `watchdog`-based background file monitor |
| `mcp_server.py` | Updated | Wires up auto-save, auto-retrieve, file watcher |

---

## Out of Scope
- Multi-user auto-save (still single-user)
- Cloud sync
- Real-time collaboration
- Web UI for configuration
- Advanced watch rules (patterns, file types)
