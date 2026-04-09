# Phase 5 Research — Auto Save, Track & Retrieve

## Phase Goals
Make the MCP server **fully automatic** — zero manual tool calls needed for save, track, or retrieve. Every conversation auto-saved to ChromaDB, every file change auto-detected via background watcher, every request auto-enriched with ~300 tokens of stored context.

### Success Criteria
- Auto-save: Every tool call/response pair captured in ChromaDB without explicit `store_chat` calls
- Auto-retrieve: ~300 tokens of relevant context injected before each tool call
- Auto-track: File changes detected in real-time via `watchdog`, auto-triggering `track_files`
- Config: `./data/config.json` toggles all three features independently
- All 191 existing tests remain passing

### Constraints
- Windows, Python 3.13.7, pip-based venv
- FastMCP 1.27.0 (no native middleware in this version)
- ChromaDB 1.5.7 (sync-only PersistentClient)
- watchdog 5.0.3 (installed, no `__version__` attr but present)
- No `pytest-asyncio` installed (tests are synchronous)

---

## Approaches Considered

### 1. FastMCP Tool Interception — Tool Wrapping vs. Low-Level Hook

**Approach A: Wrap `_tool_manager.call_tool` (Selected)**
Monkey-patch `FastMCP.call_tool` to intercept every tool invocation. Before delegating to the original, capture the call; after, capture the response. This is a single-point interception with full access to name, arguments, and result.

```python
# In mcp_server.py — after register_all()
_original_call_tool = mcp.call_tool

async def _intercepted_call_tool(name: str, arguments: dict[str, Any]):
    # BEFORE: capture tool call
    await auto_save.on_tool_call(name, arguments)
    await contextInjector.pre_tool_call(name, arguments)

    # Execute original tool
    result = await _original_call_tool(name, arguments)

    # AFTER: capture tool response
    await auto_save.on_tool_response(name, arguments, result)
    return result

mcp.call_tool = _intercepted_call_tool
```

**Pros:**
- Single interception point — all tools go through `call_tool`
- Full access to tool name, arguments, and result
- No modification to existing tool definitions
- Works with FastMCP 1.27.0 (no native middleware)
- Easy to toggle on/off via config

**Cons:**
- Monkey-patching — brittle if FastMCP internals change
- Must handle `Sequence[ContentBlock] | dict` result types
- No access to `MiddlewareContext` metadata (no session/source info in this version)

**Complexity:** Low
**Time Estimate:** 1-2 hours

**Approach B: Wrap individual tool functions**
Replace each tool's registered function with a wrapper that calls the original + auto-save logic.

**Pros:** Granular control per tool, no monkey-patching of FastMCP internals.
**Cons:** Must wrap every tool individually (9+ tools), breaks if new tools added, verbose.
**Complexity:** Medium

**Approach C: Subclass `ToolManager`**
Create a custom `ToolManager` subclass that overrides `call_tool` to add interception, then inject it into the FastMCP instance.

**Pros:** Clean OOP pattern, no monkey-patching.
**Cons:** FastMCP creates its own `_tool_manager` internally; replacing it requires digging into `__init__` internals. Risky across versions.
**Complexity:** Medium-High

**Recommended: Approach A** — `_tool_manager.call_tool` interception via `mcp.call_tool` override. It's the simplest, most robust approach for FastMCP 1.27.0. When FastMCP adds native middleware (planned for 2.x), migration is a drop-in replacement.

---

### 2. Watchdog on Windows — Observer + FileSystemEventHandler

**Approach: `Observer` + Custom `FileSystemEventHandler` (Selected)**
Use `watchdog.observers.Observer` with a custom handler subclassing `FileSystemEventHandler`. Run in a daemon background thread.

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

class AutoTrackHandler(FileSystemEventHandler):
    def __init__(self, graph: FileGraph, watch_dirs: list[str], ignore_dirs: list[str]):
        self.graph = graph
        self.watch_dirs = watch_dirs
        self.ignore_dirs = set(ignore_dirs)
        self._debounce: dict[str, float] = {}
        self._debounce_delay = 0.5  # seconds

    def on_modified(self, event):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path):
            return
        self._debounce_event(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path):
            return
        self._debounce_event(event.src_path)

    def _should_ignore(self, path: str) -> bool:
        parts = Path(path).parts
        return any(part in self.ignore_dirs for part in parts)

    def _debounce_event(self, path: str):
        """Debounce rapid-fire events (editors save multiple times)."""
        import time
        now = time.monotonic()
        last = self._debounce.get(path, 0)
        if now - last > self._debounce_delay:
            self._debounce[path] = now
            # Trigger graph update
            self.graph.update_graph(os.path.dirname(path), changed_files=[path])
```

```python
# Starting the observer
observer = Observer()
for directory in watch_dirs:
    handler = AutoTrackHandler(graph, watch_dirs, ignore_dirs)
    observer.schedule(handler, path=directory, recursive=True)
observer.start()
observer.daemon = True  # Dies when main process exits
```

**Windows Compatibility (watchdog 5.0.3):**
- Uses `ReadDirectoryChangesW` Win32 API on Windows — native, efficient
- Python 3.13 compatibility confirmed (watchdog 5.0.3 added 3.13 support in release notes)
- No special Windows handling needed — API is fully cross-platform
- **Caveat:** OneDrive synced directories (like `C:\Users\Hp\OneDrive\...`) may produce delayed or duplicate events due to OneDrive's sync layer. The debounce mechanism handles this.

**Pros:**
- Native Windows support via Win32 API
- Debouncing handles editor save storms
- `Observer` runs its own thread — no manual thread management
- `recursive=True` watches entire tree

**Cons:**
- OneDrive directories may produce delayed events
- Large directories with frequent writes generate many events
- `observer.stop()` + `observer.join()` needed for clean shutdown

**Complexity:** Low
**Time Estimate:** 2-3 hours

---

### 3. Background Threading in Async MCP Server

**Approach: Daemon Thread + Lifecycle Management (Selected)**
FastMCP's `run(transport="stdio")` blocks on `run_stdio_async()`, which runs its own event loop via `anyio`. The `watchdog.Observer` runs its own OS-native thread (not asyncio), so it coexists safely.

```python
def run_server() -> None:
    register_all()

    # Start file watcher in background thread
    watcher = None
    if config.auto_track:
        watcher = FileWatcher(config.watch_dirs, config.watch_ignore_dirs, get_graph())
        watcher.start()  # Starts observer.start() internally

    # Monkey-patch call_tool for auto-save + auto-retrieve
    if config.auto_save or config.auto_retrieve:
        _wire_interception(mcp, config)

    try:
        mcp.run(transport="stdio")  # Blocks until stdin closes
    finally:
        # Clean shutdown
        if watcher:
            watcher.stop()
        get_store().close()
```

**Key Considerations:**
- `Observer.start()` spawns its own thread — no `asyncio.create_task()` needed
- `Observer.daemon = True` ensures it dies when the main process exits
- ChromaDB `PersistentClient` is **not async** — it uses SQLite under the hood. All operations are synchronous. This is fine because:
  - Tool execution happens in async context, but we can call sync ChromaDB from async via `asyncio.to_thread()` or just call directly (SQLite handles its own locking)
  - On Windows, SQLite file locks can cause `chromadb` issues — ensure `store.close()` is called on shutdown
- **No GIL concerns:** Python 3.13 has a per-interpreter GIL (not fully free-threaded), but I/O-bound operations (ChromaDB reads, file watching) release the GIL naturally

**Windows-Specific Risks:**
- **SQLite locking:** ChromaDB uses SQLite. On Windows, multiple processes can't open the same ChromaDB path. Single-process is fine.
- **File handle leaks:** If `store.close()` isn't called, ChromaDB leaves SQLite handles open. Use `try/finally` in `run_server()`.

**Complexity:** Low
**Time Estimate:** 1 hour

---

### 4. ChromaDB Auto-Save Patterns

**Approach: Buffer + Flush on Tool Response (Selected)**
Capture each tool call/response as a document pair and save immediately to ChromaDB. No periodic batching needed — the tool response trigger is precise.

```python
class AutoSaveMiddleware:
    def __init__(self, store: ChatStore, session_id: str | None = None):
        self.store = store
        self.session_id = session_id or str(uuid.uuid4())
        self._buffer: list[dict] = []
        self._enabled = True

    async def on_tool_call(self, name: str, arguments: dict) -> None:
        """Capture tool call before execution."""
        if not self._enabled:
            return
        self._buffer.append({
            "role": "tool_call",
            "content": json.dumps({"tool": name, "arguments": arguments}),
            "session_id": self.session_id,
        })

    async def on_tool_response(self, name: str, arguments: dict, result: Any) -> None:
        """Capture tool response after execution, then flush to ChromaDB."""
        if not self._enabled:
            return
        self._buffer.append({
            "role": "tool_response",
            "content": json.dumps({"tool": name, "result": _truncate_result(result)}),
            "session_id": self.session_id,
        })
        self._flush()

    def _flush(self) -> None:
        """Flush buffer to ChromaDB."""
        if not self._buffer:
            return
        try:
            self.store.store_messages(self._buffer, session_id=self.session_id)
            self._buffer.clear()
        except Exception as e:
            logging.error(f"Auto-save failed: {e}")
            # Don't clear buffer on failure — retry next time

def _truncate_result(result: Any, max_len: int = 500) -> str:
    """Truncate tool result for storage."""
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
```

**Why direct save (not batch):**
- ChromaDB's `collection.add()` is already batched internally
- Per-tool-call saves are fine for MCP workloads (low frequency — a few calls per minute)
- Buffer ensures call+response are saved together atomically
- If the server crashes, only the current buffer is lost (1-2 messages)

**Session Management:**
- Auto-save uses its own `session_id` (auto-generated UUID at startup)
- This creates a distinct "auto-session" separate from user-initiated `store_chat` calls
- User can query auto-save history via `query_chat` with the auto-session ID

**ChromaDB Performance Notes:**
- `SentenceTransformerEmbeddingFunction` downloads ~80MB on first use (~25s)
- Embedding computation is the bottleneck (~50-100ms per document on CPU)
- For 2 messages per tool call: ~100-200ms latency added
- **Mitigation:** Embedding is already loaded by the time auto-save triggers (it's loaded during ChatStore init), so no cold start delay

**Complexity:** Low
**Time Estimate:** 2 hours

---

### 5. Context Injection Patterns

**Approach: Pre-Tool-Call Context Enrichment (Selected)**
Before each tool call executes, query ChromaDB for recent context and append it to the tool's response. This enriches the output that the LLM sees, not the input.

**Wait — reconsider:** The LLM sends tool calls; the MCP server responds. The "context injection" should enrich what the LLM *receives* — which means it should be appended to the tool response returned by the MCP server. But that changes the tool's contract. 

**Better Approach: System-Level Context via `get_context` Auto-Call**
Instead of modifying tool responses, inject context as a separate mechanism. The `ContextInjector` queries ChromaDB and stores context in a shared state that tools can optionally read. For tools that benefit from context (like query-based tools), they check the injected context.

**Simplest Approach (Selected): Append context to tool response as a structured block**
```python
class ContextInjector:
    def __init__(self, store: ChatStore, graph: FileGraph, max_tokens: int = 300):
        self.store = store
        self.graph = graph
        self.max_tokens = max_tokens
        self._enabled = True

    async def pre_tool_call(self, name: str, arguments: dict) -> str | None:
        """Query ChromaDB and return context string to append to response.
        
        Returns context string or None if no relevant context found.
        """
        if not self._enabled:
            return None

        # Build query from tool arguments
        query_text = self._extract_query(arguments)
        if not query_text:
            return None

        # Query recent context
        try:
            results = self.store.query_messages(query=query_text, top_k=3)
        except Exception:
            return None

        if not results:
            return None

        # Format to ~300 token budget
        context = format_with_detail(results, level="summary")
        if _estimate_tokens(context) > self.max_tokens:
            context = context[: self.max_tokens * 4]  # ~4 chars/token
            context += "\n...(truncated)"

        return f"\n\n[Auto-Context]\n{context}"

    def _extract_query(self, arguments: dict) -> str:
        """Extract searchable text from tool arguments."""
        # Priority: query field, content field, first string argument
        for key in ("query", "content", "message", "text", "search"):
            if key in arguments and isinstance(arguments[key], str):
                return arguments[key]
        # Fallback: concatenate all string args
        parts = [str(v) for v in arguments.values() if isinstance(v, str) and len(v) > 10]
        return " ".join(parts[:3])
```

**Integration in interception layer:**
```python
async def _intercepted_call_tool(name, arguments):
    # Pre: retrieve context
    context_block = await contextInjector.pre_tool_call(name, arguments)

    await auto_save.on_tool_call(name, arguments)
    result = await _original_call_tool(name, arguments)
    await auto_save.on_tool_response(name, arguments, result)

    # Post: append context to result
    if context_block and isinstance(result, str):
        result = result + context_block
    return result
```

**Token Budget Enforcement:**
- Use `_estimate_tokens()` from `context.py` (already exists: `len(text) // 4`)
- Cap at `max_tokens` chars (`max_tokens * 4`)
- Truncate with ellipsis

**Pros:**
- Non-invasive — doesn't modify tool contracts
- Context is clearly marked with `[Auto-Context]` header
- Token budget prevents context window overflow
- Can be toggled off per-tool or globally

**Cons:**
- Adds ChromaDB query latency to every tool call (~50-100ms)
- LLM may not know what to do with auto-context (depends on client)
- Truncation may cut off important context

**Complexity:** Medium
**Time Estimate:** 2-3 hours

---

### 6. Configuration Management

**Approach: Simple JSON File with Defaults + Validation (Selected)**
No hot-reload needed for a personal weekend tool. Load config at startup, validate against defaults, save if file doesn't exist.

```python
import json
import os
from dataclasses import dataclass, field, asdict

CONFIG_PATH = "./data/config.json"

@dataclass
class AutoConfig:
    auto_save: bool = True
    auto_retrieve: bool = True
    auto_track: bool = True
    auto_context_tokens: int = 300
    watch_dirs: list[str] = field(default_factory=lambda: ["./src"])
    watch_ignore_dirs: list[str] = field(default_factory=lambda: [
        ".git", "__pycache__", ".venv", "node_modules", "data"
    ])
    flush_interval_seconds: int = 30

    @classmethod
    def load(cls, path: str = CONFIG_PATH) -> "AutoConfig":
        """Load config from JSON file, falling back to defaults."""
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            # Merge with defaults (unknown keys ignored)
            defaults = asdict(cls())
            defaults.update({k: v for k, v in data.items() if k in defaults})
            return cls(**defaults)
        # File doesn't exist — create with defaults
        config = cls()
        config.save(path)
        return config

    def save(self, path: str = CONFIG_PATH) -> None:
        """Save config to JSON file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)
```

**Why dataclass (not pydantic):**
- Project already uses pydantic for MCP tool annotations, but a dataclass is lighter for simple config
- `asdict()` provides easy JSON serialization
- `field(default_factory=...)` handles mutable defaults correctly
- No external dependencies needed

**Validation:**
- Type hints provide IDE autocomplete
- Constructor validation (e.g., `auto_context_tokens > 0`) can be added via `__post_init__`
- Unknown keys in JSON are silently ignored (forward-compatible)

```python
def __post_init__(self):
    if self.auto_context_tokens < 50:
        self.auto_context_tokens = 50  # Minimum
    if self.auto_context_tokens > 2000:
        self.auto_context_tokens = 2000  # Maximum
    if self.flush_interval_seconds < 5:
        self.flush_interval_seconds = 5
```

**Pros:**
- Human-editable JSON
- Version-controllable
- Zero dependencies
- Forward-compatible (unknown keys ignored)

**Cons:**
- No hot-reload (requires server restart to apply changes)
- No schema validation for typos in keys

**Complexity:** Low
**Time Estimate:** 1 hour

---

### 7. Testing Strategies for Async + Threading

**Approach: Synchronous Tests with Mocked Observer (Matches existing patterns)**
The project uses synchronous pytest (no `pytest-asyncio`). Continue this pattern:

**Test 1: ConfigManager**
```python
def test_config_loads_defaults(tmp_path):
    path = str(tmp_path / "config.json")
    config = AutoConfig.load(path)
    assert config.auto_save is True
    assert config.auto_context_tokens == 300
    assert os.path.exists(path)  # File created

def test_config_merges_with_defaults(tmp_path):
    path = str(tmp_path / "config.json")
    with open(path, "w") as f:
        json.dump({"auto_save": False, "unknown_key": "ignored"}, f)
    config = AutoConfig.load(path)
    assert config.auto_save is False
    assert config.auto_retrieve is True  # Default preserved
```

**Test 2: AutoSaveMiddleware**
```python
def test_auto_save_captures_tool_calls(store):
    middleware = AutoSaveMiddleware(store, session_id="test-session")
    # Simulate tool call + response
    middleware.on_tool_call("ping", {})
    middleware.on_tool_response("ping", {}, '{"status": "ok"}')
    # Verify saved to ChromaDB
    results = store.query_messages("ping", session_id="test-session")
    assert len(results) >= 2

def test_auto_save_truncates_large_results(store):
    middleware = AutoSaveMiddleware(store, session_id="test-session")
    large_result = "x" * 2000
    middleware.on_tool_call("test", {})
    middleware.on_tool_response("test", {}, large_result)
    results = store.query_messages("test", session_id="test-session")
    # Find the response message
    response = [r for r in results if "tool_response" in r.get("content", "")]
    assert len(response) > 0
    assert len(response[0]["content"]) < 1000  # Truncated
```

**Test 3: FileWatcher (Mocked Observer)**
```python
@patch("context_memory_mcp.file_watcher.Observer")
def test_file_watcher_starts_and_stops(mock_observer_class):
    mock_observer = MagicMock()
    mock_observer_class.return_value = mock_observer
    watcher = FileWatcher(["./src"], [".git"], get_graph())
    watcher.start()
    mock_observer.start.assert_called_once()
    watcher.stop()
    mock_observer.stop.assert_called_once()
    mock_observer.join.assert_called_once()

def test_file_watcher_ignores_skip_dirs(tmp_path):
    handler = AutoTrackHandler(get_graph(), [str(tmp_path)], [".git", "__pycache__"])
    # Create a mock event
    event = MagicMock()
    event.is_directory = False
    event.src_path = str(tmp_path / "__pycache__" / "module.pyc")
    handler.on_modified(event)
    # Should be ignored — no graph update triggered
```

**Test 4: ContextInjector**
```python
def test_context_injector_returns_context_when_messages_exist(store):
    # Populate ChromaDB
    store.store_messages([
        {"role": "user", "content": "How does ChromaDB work?"},
        {"role": "assistant", "content": "ChromaDB is a vector database..."},
    ], session_id="ctx-test")

    injector = ContextInjector(store, get_graph(), max_tokens=300)
    context = injector.pre_tool_call("query_chat", {"query": "vector database"})
    assert context is not None
    assert "Auto-Context" in context
    assert _estimate_tokens(context) <= 300

def test_context_injector_returns_none_when_no_messages(store):
    injector = ContextInjector(store, get_graph(), max_tokens=300)
    context = injector.pre_tool_call("ping", {})
    assert context is None
```

**Test 5: End-to-End Integration**
```python
def test_full_auto_pipeline(tmp_path):
    """Chat → auto-save → auto-retrieve → file change → auto-track."""
    # Setup
    store = ChatStore(chroma_path=str(tmp_path / "chromadb"), ...)
    middleware = AutoSaveMiddleware(store)
    injector = ContextInjector(store, ...)

    # Auto-save: simulate tool interaction
    middleware.on_tool_call("ping", {})
    middleware.on_tool_response("ping", {}, '{"status":"ok"}')

    # Verify saved
    results = store.query_messages("ping", session_id=middleware.session_id)
    assert len(results) >= 2

    # Auto-retrieve: query context
    context = injector.pre_tool_call("ping", {})
    assert "Auto-Context" in context  # Context found from auto-save
```

**Key Testing Patterns:**
- Use `tmp_path` fixture for isolated ChromaDB directories
- Mock `Observer` class to avoid real file system events
- Test `AutoTrackHandler` directly with mock events (no threading)
- Use `store.close()` in fixture teardown
- No `pytest-asyncio` needed — `AutoSaveMiddleware` methods can be sync (they call sync ChromaDB)

**Complexity:** Medium
**Time Estimate:** 3-4 hours

---

## Recommended Approach

**Selected:** Combination of all selected approaches above

**Why:** Each approach is independently validated and compatible with the existing codebase patterns. The monkey-patch interception is the weakest link but is acceptable for FastMCP 1.27.0 with a clear migration path to native middleware in 2.x.

### Implementation Notes

1. **Order of operations in `mcp_server.py`:**
   ```
   register_all() → load config → start watcher → wire interception → mcp.run()
   ```

2. **Auto-save session isolation:** Use a dedicated `session_id` for auto-saved interactions. This keeps auto-save history queryable separately from user-initiated `store_chat` sessions.

3. **Result type handling:** `call_tool` returns `Sequence[ContentBlock] | dict`. When it's `ContentBlock`, extract text from `block.text` or `block.content` for storage. Most tools return JSON strings, so `isinstance(result, str)` covers 90% of cases.

4. **Debounce is critical:** Editors (VS Code, etc.) fire multiple save events per file edit. Without debouncing, the graph updates 3-5x per save. Use `time.monotonic()` with a 0.5s window.

5. **Graceful shutdown order:**
   ```
   1. Stop file watcher (observer.stop() + observer.join())
   2. Flush auto-save buffer
   3. Close ChromaDB (store.close())
   ```

6. **Context injection is optional per-tool:** Skip injection for `ping` and `get_file_graph` — they don't benefit from chat context. Only inject for tools that process queries or content.

### Libraries/Tools

| Library | Version | Why |
|---------|---------|-----|
| `watchdog` | 5.0.3 (installed) | Cross-platform file system monitoring, native Windows support |
| `chromadb` | 1.5.7 (installed) | Sync PersistentClient — already used, no new deps |
| `dataclasses` | stdlib | Lightweight config management, no deps |
| `unittest.mock` | stdlib | Mock Observer for testing, no deps |

**New dependency needed:** `watchdog` (already installed at 5.0.3). Add to `pyproject.toml`:
```toml
dependencies = [
    ...existing...,
    "watchdog>=5.0.0",
]
```

### Pitfalls to Avoid

1. **Don't call `asyncio.to_thread()` for ChromaDB** — ChromaDB's sync API works fine in async context for low-frequency calls. The overhead isn't worth it.

2. **Don't modify `ContentBlock` results** — If `call_tool` returns `Sequence[ContentBlock]`, appending a string breaks the type contract. Check `isinstance(result, str)` before concatenation.

3. **Don't start watcher on non-existent directories** — `observer.schedule()` raises `FileNotFoundError` if the path doesn't exist. Validate paths exist before scheduling.

4. **Don't forget `observer.join()` on shutdown** — Without it, the observer thread may still be processing events when the process exits, potentially leaving file handles open.

5. **Don't embed auto-context in non-query tools** — Injecting context into `ping` or `list_sessions` adds noise without value. Only inject for tools that process text content.

6. **OneDrive sync delays** — The project is in `OneDrive\Desktop\memory`. OneDrive's sync layer can delay or duplicate file events. The 0.5s debounce handles this, but be aware that `on_modified` may fire 2-3 seconds after the actual save.

7. **ChromaDB SQLite locks on Windows** — If tests fail with "database is locked" errors, ensure `store.close()` is called in every test teardown. The `@pytest.fixture` pattern in `conftest.py` already handles this for existing tests.

### Codebase Patterns (if brownfield)

- **Follow singleton pattern:** `get_store()`, `get_graph()` — create `get_config()` for config
- **Follow `register(mcp)` pattern:** Each module exports `register(mcp: FastMCP)` — auto-save/retrieve don't need this (they're middleware, not tools)
- **Integrate with `ChatStore`:** Auto-save reuses existing `store_messages()` and `query_messages()` APIs
- **Integrate with `FileGraph`:** Auto-track reuses existing `update_graph()` API with explicit `changed_files` parameter
- **Integrate with `context.py`:** Reuse `format_with_detail()` and `_estimate_tokens()` for context formatting
- **Follow test patterns:** `tmp_path` fixtures, isolated ChromaDB paths, `store.close()` in teardown
- **Import style:** `from __future__ import annotations` at top of every file (consistent with all existing modules)

---

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| FastMCP `call_tool` signature changes in update | Medium | Medium | Pin `mcp>=1.0.0,<2.0.0`; add version check in `_wire_interception()` |
| ChromaDB embedding latency adds noticeable delay | Low | Low | Embedding is pre-loaded; ~50ms per query is acceptable |
| Watchdog misses events on OneDrive dirs | Medium | Low | Graceful degradation — user can still call `track_files` manually |
| Auto-context overwhelms LLM context window | Low | Medium | Strict token budget (300), configurable, truncation with ellipsis |
| Background thread interferes with async event loop | Low | High | Observer uses OS thread, not asyncio — completely isolated |
| Tests flaky due to threading timing | Low | Medium | Mock Observer in tests, never start real thread in test mode |
