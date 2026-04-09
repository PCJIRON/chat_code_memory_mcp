---
phase: 5
plan: 01
type: feature
wave: 1
depends_on: []
---

## Objective
Implement fully automatic behavior for the Context Memory MCP server: every tool call/response auto-saved to ChromaDB, every request auto-enriched with ~300 tokens of stored context, and every file change auto-detected via background `watchdog` file watcher — all toggled via `./data/config.json`.

## Context
- **Research:** `.planning/5-RESEARCH.md` — FastMCP has no native middleware (monkey-patch `mcp.call_tool`), watchdog 5.0.3 already installed, OneDrive dirs need 0.5s debounce, `watchdog.Observer` runs its own OS thread, ChromaDB auto-save via existing `store_messages()` API, context injection reuses `format_with_detail()` and `_estimate_tokens()`, config via Python dataclass with JSON serialization.
- **Decisions:** `.planning/5-CONTEXT.md` — Server-side interception (Decision 1), `ContextInjector` with ~300 token budget (Decision 2), `watchdog` background thread (Decision 3), auto-save on tool response (Decision 4), ~300 tokens summary level (Decision 5), `./data/config.json` with toggle features (Decision 6).
- **Current state:** Phases 1-4 complete, 191 tests passing. `src/context_memory_mcp/` package with existing modules: `chat_store.py`, `context.py`, `file_graph.py`, `parser.py`, `mcp_server.py`. `watchdog` 5.0.3 already installed.
- **Commit format:** `[GSD-5-01-T{N}] description`

---

## Wave 1: Configuration Manager (no dependencies)

### T1: Create `src/context_memory_mcp/config.py` — `AutoConfig` dataclass
**Type:** auto
**Dependencies:** none
**Estimated effort:** 30 min

Create `AutoConfig` dataclass with `load()`/`save()` methods for `./data/config.json`:

**Fields:**
- `auto_save: bool = True`
- `auto_retrieve: bool = True`
- `auto_track: bool = True`
- `auto_context_tokens: int = 300`
- `watch_dirs: list[str] = field(default_factory=lambda: ["./src"])`
- `watch_ignore_dirs: list[str] = field(default_factory=lambda: [".git", "__pycache__", ".venv", "node_modules", "data"])`
- `flush_interval_seconds: int = 30`

**Methods:**
- `@classmethod load(cls, path=CONFIG_PATH)` — load JSON, merge with defaults, create file if missing
- `save(self, path=CONFIG_PATH)` — serialize `asdict(self)` to JSON, create parent dirs
- `__post_init__` — validate `auto_context_tokens` in [50, 2000], `flush_interval_seconds` >= 5

**File to create:** `src/context_memory_mcp/config.py`
**Add to `__init__.py`:** export `AutoConfig` and `get_config()` singleton helper (follow `get_store()` pattern)

**Success criteria:**
- [ ] `AutoConfig.load()` on non-existent path creates `./data/config.json` with defaults
- [ ] `AutoConfig.load()` on partial JSON preserves missing defaults
- [ ] Unknown keys in JSON are silently ignored
- [ ] `__post_init__` clamps `auto_context_tokens` to [50, 2000]
- [ ] `get_config()` returns singleton (same instance on repeated calls)
- [ ] Imports work: `from context_memory_mcp.config import AutoConfig, get_config`

**Commit scope:** `[GSD-5-01-T1] create AutoConfig dataclass with load/save and validation`

---

## Wave 2: Auto-Save Middleware (depends on T1)

### T2: Create `src/context_memory_mcp/auto_save.py` — `AutoSaveMiddleware` class
**Type:** auto
**Dependencies:** T1
**Estimated effort:** 1.5 hours

Implement `AutoSaveMiddleware` that intercepts tool calls/responses and buffers them for ChromaDB storage:

**Class structure:**
```python
class AutoSaveMiddleware:
    def __init__(self, store: ChatStore, config: AutoConfig | None = None, session_id: str | None = None):
        # Store reference, config (default from get_config()), auto-generate session_id via uuid4()
        # Initialize _buffer: list[dict] and _enabled flag from config.auto_save

    def on_tool_call(self, name: str, arguments: dict) -> None:
        # If not enabled, return early
        # Append {"role": "tool_call", "content": json.dumps({"tool": name, "arguments": arguments}), "session_id": self.session_id} to _buffer

    def on_tool_response(self, name: str, arguments: dict, result: Any) -> None:
        # If not enabled, return early
        # Append {"role": "tool_response", "content": json.dumps({"tool": name, "result": _truncate_result(result)}), "session_id": self.session_id} to _buffer
        # Call _flush()

    def _flush(self) -> None:
        # If buffer empty, return
        # try: self.store.store_messages(self._buffer, session_id=self.session_id); self._buffer.clear()
        # except Exception as e: log.error (don't clear on failure)
```

**Helper function:**
```python
def _truncate_result(result: Any, max_len: int = 500) -> str:
    # If result is str, use it; else json.dumps(result, default=str)
    # Truncate to max_len + "..." if exceeded
```

**Sync vs Async:** All methods are **synchronous** — ChromaDB `store_messages()` is sync, no `asyncio.to_thread()` needed (per 5-RESEARCH.md Pitfall #1).

**File to create:** `src/context_memory_mcp/auto_save.py`

**Success criteria:**
- [ ] `AutoSaveMiddleware(store)` initializes with auto-generated session_id (UUID format)
- [ ] `on_tool_call` + `on_tool_response` adds 2 entries to buffer
- [ ] `_flush()` calls `store.store_messages()` and clears buffer
- [ ] `_flush()` does NOT clear buffer on exception (retry-safe)
- [ ] `_truncate_result` truncates strings > 500 chars with "..."
- [ ] `_truncate_result` handles non-string results (dicts, lists) via `json.dumps`
- [ ] `on_tool_call/response` are no-ops when `_enabled = False`
- [ ] Disabled via config when `config.auto_save = False`

**Commit scope:** `[GSD-5-01-T2] implement AutoSaveMiddleware with buffer and flush to ChromaDB`

### T3: Add tests for `AutoSaveMiddleware`
**Type:** auto
**Dependencies:** T2
**Estimated effort:** 1 hour

Create `tests/test_auto_save.py` with synchronous pytest tests (no `pytest-asyncio`):

**Test cases:**
1. `test_auto_save_initializes_with_session_id` — session_id is valid UUID string
2. `test_auto_save_captures_tool_call_and_response` — call + response → 2 items in buffer, then flushed to ChromaDB
3. `test_auto_save_truncates_large_results` — 2000-char result → truncated to < 1000 chars in stored message
4. `test_auto_save_disabled_does_nothing` — set `_enabled = False`, call on_tool_call/response, verify buffer stays empty
5. `test_auto_save_flush_failure_preserves_buffer` — mock `store_messages` to raise, verify buffer NOT cleared
6. `test_auto_save_respects_config_toggle` — `AutoConfig(auto_save=False)` → middleware disabled
7. `test_auto_save_session_isolation` — query with middleware's session_id returns auto-saved messages, not user-initiated ones

**Use fixtures:**
- `tmp_path` for isolated ChromaDB directory
- Existing `conftest.py` Windows DLL fix applies
- Call `store.close()` in teardown

**File to create:** `tests/test_auto_save.py`

**Success criteria:**
- [ ] All 7 tests pass with `pytest tests/test_auto_save.py -v`
- [ ] Tests use `tmp_path` for ChromaDB isolation
- [ ] No real file system events triggered (no threading in tests)

**Commit scope:** `[GSD-5-01-T3] add pytest tests for AutoSaveMiddleware CRUD and edge cases`

---

## Wave 3: Context Injector (depends on T1, T2)

### T4: Create `src/context_memory_mcp/auto_retrieve.py` — `ContextInjector` class
**Type:** auto
**Dependencies:** T1, T2 (shares `ChatStore` reference)
**Estimated effort:** 1.5 hours

Implement `ContextInjector` that queries ChromaDB before each tool call and returns a context string to append to the response:

**Class structure:**
```python
class ContextInjector:
    def __init__(self, store: ChatStore, config: AutoConfig | None = None, graph: FileGraph | None = None):
        # Store reference, config (default from get_config()), optional graph
        # self.max_tokens = config.auto_context_tokens if config else 300
        # self._enabled = config.auto_retrieve if config else True

    def pre_tool_call(self, name: str, arguments: dict) -> str | None:
        # If not enabled, return None
        # Extract query text from arguments via _extract_query(arguments)
        # If no query text, return None
        # try: results = self.store.query_messages(query=query_text, top_k=3)
        # except Exception: return None
        # If no results, return None
        # context = format_with_detail(results, level="summary")
        # If _estimate_tokens(context) > self.max_tokens: truncate + "...\n(truncated)"
        # return f"\n\n[Auto-Context]\n{context}"

    def _extract_query(self, arguments: dict) -> str:
        # Priority: "query", "content", "message", "text", "search" keys
        # Fallback: concatenate all string values > 10 chars (first 3)
        # Return empty string if nothing found
```

**Key decisions from 5-CONTEXT.md:**
- Uses `format_with_detail(level="summary")` from `context.py` (Decision 2)
- Uses `_estimate_tokens()` from `context.py` for token budget enforcement (Decision 5)
- ~300 token budget, configurable via `auto_context_tokens`
- Returns `None` when no context found (caller checks before appending)
- Context clearly marked with `[Auto-Context]` header

**Skip injection for non-query tools:** The wiring layer (T7) will check tool name and skip `pre_tool_call` for `ping`, `list_sessions`, `get_file_graph` etc.

**File to create:** `src/context_memory_mcp/auto_retrieve.py`

**Success criteria:**
- [ ] `ContextInjector(store)` initializes with `max_tokens=300` default
- [ ] `pre_tool_call("query_chat", {"query": "vector db"})` returns string with `[Auto-Context]` header when ChromaDB has messages
- [ ] `pre_tool_call("ping", {})` returns `None` (no query text in args)
- [ ] `pre_tool_call` returns `None` when `_enabled = False`
- [ ] `pre_tool_call` returns `None` when ChromaDB has no matching messages
- [ ] Context is truncated when `_estimate_tokens()` exceeds `max_tokens`
- [ ] `_extract_query` finds query text from various argument key names
- [ ] `_extract_query` falls back to concatenating long string values

**Commit scope:** `[GSD-5-01-T4] implement ContextInjector with ChromaDB query and token budget enforcement`

### T5: Add tests for `ContextInjector`
**Type:** auto
**Dependencies:** T4
**Estimated effort:** 45 min

Create `tests/test_auto_retrieve.py` with synchronous pytest tests:

**Test cases:**
1. `test_context_injector_returns_context_when_messages_exist` — populate ChromaDB, call `pre_tool_call`, verify `[Auto-Context]` in result
2. `test_context_injector_returns_none_when_no_messages` — empty ChromaDB → `None`
3. `test_context_injector_returns_none_when_disabled` — `_enabled = False` → `None`
4. `test_context_injector_respects_token_budget` — set `max_tokens=50`, verify `_estimate_tokens(result) <= 50`
5. `test_context_injector_extracts_query_from_args` — test `_extract_query` with `{"query": "..."}`, `{"content": "..."}`, `{"foo": "bar"}` (fallback)
6. `test_context_injector_handles_query_exception` — mock `query_messages` to raise, verify returns `None`

**File to create:** `tests/test_auto_retrieve.py`

**Success criteria:**
- [ ] All 6 tests pass with `pytest tests/test_auto_retrieve.py -v`
- [ ] Tests use `tmp_path` for ChromaDB isolation
- [ ] Token budget enforcement verified

**Commit scope:** `[GSD-5-01-T5] add pytest tests for ContextInjector query and token budget`

---

## Wave 4: File Watcher (depends on T1)

### T6: Create `src/context_memory_mcp/file_watcher.py` — `FileWatcher` + `AutoTrackHandler`
**Type:** auto
**Dependencies:** T1
**Estimated effort:** 2 hours

Implement `watchdog`-based background file monitoring:

**Handler class:**
```python
class AutoTrackHandler(FileSystemEventHandler):
    def __init__(self, graph: FileGraph, watch_dirs: list[str], ignore_dirs: list[str]):
        self.graph = graph
        self.watch_dirs = watch_dirs
        self.ignore_dirs = set(ignore_dirs)
        self._debounce: dict[str, float] = {}
        self._debounce_delay = 0.5  # seconds (per 5-RESEARCH.md — OneDrive handling)

    def on_modified(self, event):
        if event.is_directory: return
        if self._should_ignore(event.src_path): return
        self._debounce_event(event.src_path)

    def on_created(self, event):
        if event.is_directory: return
        if self._should_ignore(event.src_path): return
        self._debounce_event(event.src_path)

    def _should_ignore(self, path: str) -> bool:
        # Check if any part of path is in ignore_dirs
        return any(part in self.ignore_dirs for part in Path(path).parts)

    def _debounce_event(self, path: str):
        # time.monotonic() check against self._debounce.get(path, 0)
        # If > _debounce_delay: update debounce dict, call self.graph.update_graph(dirname, changed_files=[path])
```

**Watcher class:**
```python
class FileWatcher:
    def __init__(self, watch_dirs: list[str], ignore_dirs: list[str], graph: FileGraph):
        self.graph = graph
        self.watch_dirs = watch_dirs
        self.ignore_dirs = ignore_dirs
        self._observer = Observer()
        self._running = False

    def start(self) -> None:
        # Validate dirs exist (skip non-existent, log warning)
        # Create handler = AutoTrackHandler(self.graph, self.watch_dirs, self.ignore_dirs)
        # For each existing dir: self._observer.schedule(handler, path=dir, recursive=True)
        # self._observer.daemon = True
        # self._observer.start()
        # self._running = True

    def stop(self) -> None:
        # if self._running: self._observer.stop(); self._observer.join(timeout=5); self._running = False
```

**Key decisions from 5-RESEARCH.md:**
- `Observer` runs its own OS thread — no `asyncio.create_task()` needed
- `daemon = True` ensures it dies when main process exits
- 0.5s debounce handles OneDrive delayed/duplicate events
- Validate dirs exist before scheduling (Pitfall #3)
- Must call `observer.stop()` + `observer.join()` for clean shutdown (Pitfall #4)

**File to create:** `src/context_memory_mcp/file_watcher.py`

**Success criteria:**
- [ ] `FileWatcher(["./src"], [".git"], graph).start()` starts observer thread
- [ ] `FileWatcher.stop()` stops and joins observer (no hanging)
- [ ] `AutoTrackHandler._should_ignore` correctly ignores `.git`, `__pycache__` paths
- [ ] `AutoTrackHandler._debounce_event` delays rapid-fire events (0.5s window)
- [ ] Non-existent watch dirs are skipped (no exception)
- [ ] `on_modified` for directory events is a no-op
- [ ] `on_created` for new files triggers `graph.update_graph`

**Commit scope:** `[GSD-5-01-T6] implement FileWatcher with watchdog Observer and debounced AutoTrackHandler`

### T7: Add tests for `FileWatcher`
**Type:** auto
**Dependencies:** T6
**Estimated effort:** 45 min

Create `tests/test_file_watcher.py` with synchronous pytest tests using mocked `Observer`:

**Test cases:**
1. `test_file_watcher_starts_and_stops` — mock `Observer`, verify `start()` and `stop()` + `join()` called
2. `test_file_watcher_ignores_skip_dirs` — `AutoTrackHandler._should_ignore` returns `True` for `.git`, `__pycache__` paths
3. `test_file_watcher_ignores_directories` — `on_modified` with `event.is_directory = True` is no-op
4. `test_file_watcher_debounces_rapid_events` — two events within 0.5s → only first triggers graph update
5. `test_file_watcher_skips_nonexistent_dirs` — `FileWatcher` with non-existent path → no exception, only existing dirs scheduled
6. `test_file_watcher_handler_tracks_file_changes` — `on_modified` triggers `graph.update_graph` with correct `changed_files`

**Mocking pattern:**
```python
@patch("context_memory_mcp.file_watcher.Observer")
def test_file_watcher_starts_and_stops(mock_observer_class):
    mock_observer = MagicMock()
    mock_observer_class.return_value = mock_observer
    watcher = FileWatcher(["./src"], [".git"], MagicMock())  # Mock graph too
    watcher.start()
    mock_observer.start.assert_called_once()
    watcher.stop()
    mock_observer.stop.assert_called_once()
    mock_observer.join.assert_called_once()
```

**File to create:** `tests/test_file_watcher.py`

**Success criteria:**
- [ ] All 6 tests pass with `pytest tests/test_file_watcher.py -v`
- [ ] No real `Observer` threads started in tests (fully mocked)
- [ ] Debounce timing tested with `time.monotonic` mocking or `time.sleep(0.6)`

**Commit scope:** `[GSD-5-01-T7] add pytest tests for FileWatcher with mocked Observer`

---

## Wave 5: Wiring + Integration (depends on T1-T7)

### T8: Wire auto-save + auto-retrieve + file watcher into `mcp_server.py`
**Type:** checkpoint
**Dependencies:** T1, T2, T4, T6
**Estimated effort:** 1.5 hours

Update `src/context_memory_mcp/mcp_server.py` to wire all automatic features:

**Changes to `run_server()`:**
```python
def run_server() -> None:
    register_all()

    # Load config
    from context_memory_mcp.config import get_config
    config = get_config()

    # Get singletons
    from context_memory_mcp.chat_store import get_store
    from context_memory_mcp.file_graph import get_graph
    store = get_store()
    graph = get_graph()

    # Start file watcher in background thread
    watcher = None
    if config.auto_track:
        from context_memory_mcp.file_watcher import FileWatcher
        watcher = FileWatcher(config.watch_dirs, config.watch_ignore_dirs, graph)
        watcher.start()

    # Wire interception for auto-save + auto-retrieve
    if config.auto_save or config.auto_retrieve:
        _wire_interception(mcp, config, store, graph)

    try:
        mcp.run(transport="stdio")  # Blocks until stdin closes
    finally:
        # Clean shutdown
        if watcher:
            watcher.stop()
        store.close()
```

**New function `_wire_interception`:**
```python
def _wire_interception(mcp: FastMCP, config: AutoConfig, store: ChatStore, graph: FileGraph) -> None:
    """Monkey-patch mcp.call_tool for auto-save and auto-retrieve."""
    from context_memory_mcp.auto_save import AutoSaveMiddleware
    from context_memory_mcp.auto_retrieve import ContextInjector

    auto_save = AutoSaveMiddleware(store, config)
    context_injector = ContextInjector(store, config, graph)

    _original_call_tool = mcp.call_tool

    async def _intercepted_call_tool(name: str, arguments: dict[str, Any]):
        # Pre-tool: retrieve context (if enabled and tool benefits from context)
        context_block = None
        if config.auto_retrieve and name not in ("ping", "list_sessions", "get_file_graph", "delete_session"):
            context_block = context_injector.pre_tool_call(name, arguments)

        # Pre-tool: capture tool call for auto-save
        if config.auto_save:
            auto_save.on_tool_call(name, arguments)

        # Execute original tool
        result = await _original_call_tool(name, arguments)

        # Post-tool: capture tool response for auto-save
        if config.auto_save:
            auto_save.on_tool_response(name, arguments, result)

        # Post-tool: append context to result (only if string)
        if context_block and isinstance(result, str):
            result = result + context_block

        return result

    mcp.call_tool = _intercepted_call_tool
```

**Key decisions:**
- Skip context injection for non-query tools: `ping`, `list_sessions`, `get_file_graph`, `delete_session` (per 5-RESEARCH.md Pitfall #5)
- `call_tool` returns `Sequence[ContentBlock] | dict` — check `isinstance(result, str)` before appending context (Pitfall #2)
- All auto-save methods are sync (no `await` needed)
- Graceful shutdown order: watcher → store (per 5-RESEARCH.md graceful shutdown)

**File to modify:** `src/context_memory_mcp/mcp_server.py`

**Success criteria:**
- [ ] Server starts without error when all features enabled
- [ ] `config.auto_save = False` → no interception wired
- [ ] `config.auto_track = False` → no watcher started
- [ ] `config.auto_retrieve = False` → no context injection
- [ ] Server shuts down cleanly (watcher stopped, store closed) on stdin close
- [ ] Monkey-patched `call_tool` delegates to original correctly
- [ ] Context appended to string results, non-string results unchanged

**⚠️ CHECKPOINT:** This task modifies the core server behavior. Review the interception logic carefully — ensure `_original_call_tool` signature matches FastMCP's `call_tool(name, arguments)` exactly. Verify that `result` type handling covers both `str` and `Sequence[ContentBlock]` cases.

**Commit scope:** `[GSD-5-01-T8] wire auto-save, auto-retrieve, and file watcher into mcp_server with monkey-patched call_tool`

---

## Wave 6: End-to-End Testing (depends on T8)

### T9: End-to-end integration test — full auto pipeline
**Type:** auto
**Dependencies:** T8
**Estimated effort:** 1.5 hours

Create `tests/test_auto_integration.py` with end-to-end tests that verify the complete auto-save → auto-retrieve → auto-track pipeline:

**Test cases:**
1. `test_full_auto_pipeline` — Simulate: (a) tool call + response → auto-save captures; (b) query context → auto-retrieve finds saved messages; (c) verify `[Auto-Context]` in result
2. `test_auto_save_session_isolation_e2e` — Auto-save uses distinct session_id, query by that session returns only auto-saved messages
3. `test_auto_retrieve_respects_token_budget_e2e` — Store many messages, verify context injected is within token budget
4. `test_disabled_features_do_not_interfere` — Set `auto_save=False, auto_retrieve=False, auto_track=False`, verify tools still work normally

**Testing approach (no real threading):**
- Test `AutoSaveMiddleware` and `ContextInjector` synchronously (no monkey-patching in tests)
- Mock `Observer` for file watcher tests
- Use `tmp_path` for isolated ChromaDB
- Verify buffer flush, context formatting, and session isolation

**File to create:** `tests/test_auto_integration.py`

**Success criteria:**
- [ ] All 4 integration tests pass with `pytest tests/test_auto_integration.py -v`
- [ ] Tests verify complete pipeline: save → retrieve → context injection
- [ ] Disabled feature test confirms graceful degradation
- [ ] No real file watcher threads started in tests

**Commit scope:** `[GSD-5-01-T9] add end-to-end integration tests for full auto pipeline`

### T10: Run full test suite, verify server starts, create summary
**Type:** checkpoint
**Dependencies:** T9
**Estimated effort:** 30 min

Run `pytest tests/ -v` to verify all 191 + new tests pass. Verify:

1. **Full test suite:** `pytest tests/ -v --tb=short` — all tests pass
2. **Server starts:** `python -m context_memory_mcp` (brief smoke test, it will block on stdio)
3. **Config file created:** `./data/config.json` exists with defaults
4. **No import errors:** `python -c "from context_memory_mcp.config import get_config; from context_memory_mcp.auto_save import AutoSaveMiddleware; from context_memory_mcp.auto_retrieve import ContextInjector; from context_memory_mcp.file_watcher import FileWatcher; print('All imports OK')"`

**Create `.planning/5-01-SUMMARY.md`** documenting:
- Test results (pass/fail counts)
- Any deviations from plan
- Known limitations
- Next steps

**Success criteria:**
- [ ] All tests pass (191 existing + 23 new = ~214 total)
- [ ] No import errors
- [ ] `./data/config.json` created with correct defaults
- [ ] `5-01-SUMMARY.md` created with execution results
- [ ] Server starts without crash (manual smoke test)

**⚠️ CHECKPOINT:** Before proceeding to ship phase, verify all tests pass and review the SUMMARY.md for any deviations that need user approval.

**Commit scope:** `[GSD-5-01-T10] run full test suite, verify server starts, create 5-01-SUMMARY.md`

---

## Wave 7: Documentation (depends on T10)

### T11: Update README.md — document automatic behavior
**Type:** auto
**Dependencies:** T10
**Estimated effort:** 30 min

Update `README.md` to document:

1. **New automatic features section:**
   - Auto-Save: Every tool call/response automatically saved to ChromaDB
   - Auto-Retrieve: ~300 tokens of context injected before each request
   - Auto-Track: Background file watcher monitors `./src` for changes

2. **Configuration options:**
   - `./data/config.json` structure and all fields
   - How to toggle features on/off
   - How to adjust `auto_context_tokens` budget
   - How to configure `watch_dirs` and `watch_ignore_dirs`

3. **Architecture diagram** (ASCII):
   ```
   Tool Call ──→ AutoSaveMiddleware ──→ ChromaDB
                 │
                 ├── ContextInjector ──→ ~300 tokens appended
                 │
                 └── Original Tool ──→ Response
   ```

4. **No breaking changes** — all features are opt-in via config (default: enabled)

**File to modify:** `README.md`

**Success criteria:**
- [ ] README documents all three automatic features
- [ ] Config JSON structure documented with example
- [ ] Architecture diagram included
- [ ] No outdated information from previous phases

**Commit scope:** `[GSD-5-01-T11] update README with auto-save, auto-retrieve, auto-track documentation`

---

## Verification

### Wave 1 Verification (T1)
- [ ] `AutoConfig.load()` creates `./data/config.json` with all 7 fields
- [ ] `AutoConfig.load()` merges partial JSON with defaults correctly
- [ ] `get_config()` returns singleton
- [ ] `__post_init__` clamps values correctly

### Wave 2 Verification (T2-T3)
- [ ] `AutoSaveMiddleware` buffers call+response pairs and flushes to ChromaDB
- [ ] `_truncate_result` handles strings and non-strings
- [ ] Disabled middleware is no-op
- [ ] All 7 tests in `test_auto_save.py` pass

### Wave 3 Verification (T4-T5)
- [ ] `ContextInjector.pre_tool_call` returns `[Auto-Context]` string when context found
- [ ] Returns `None` when no context, disabled, or no query text
- [ ] Token budget enforced via `_estimate_tokens()`
- [ ] All 6 tests in `test_auto_retrieve.py` pass

### Wave 4 Verification (T6-T7)
- [ ] `FileWatcher.start()` starts observer thread
- [ ] `FileWatcher.stop()` stops and joins cleanly
- [ ] `AutoTrackHandler` debounces rapid events (0.5s)
- [ ] `AutoTrackHandler` ignores directories and configured paths
- [ ] All 6 tests in `test_file_watcher.py` pass

### Wave 5 Verification (T8)
- [ ] Server starts with all features enabled
- [ ] Server starts with individual features disabled
- [ ] Monkey-patched `call_tool` delegates to original
- [ ] Context appended to string results only
- [ ] Clean shutdown on stdin close

### Wave 6 Verification (T9-T10)
- [ ] All 4 integration tests pass
- [ ] Full test suite: 214+ tests pass
- [ ] No import errors
- [ ] `5-01-SUMMARY.md` created

### Wave 7 Verification (T11)
- [ ] README documents auto-save, auto-retrieve, auto-track
- [ ] Config JSON structure documented
- [ ] Architecture diagram included

## Dependencies

```
Wave 1 (T1) ──────────────────────────────────────────────→ Config
    │
    ├──→ Wave 2 (T2-T3) ──────────────────────────────────→ AutoSave
    │         │
    │         └──→ Wave 3 (T4-T5) ────────────────────────→ ContextInjector
    │
    └──→ Wave 4 (T6-T7) ──────────────────────────────────→ FileWatcher
              │
              └──→ Wave 5 (T8) ───────────────────────────→ Wiring
                        │
                        └──→ Wave 6 (T9-T10) ────────────→ E2E Tests
                                      │
                                      └──→ Wave 7 (T11) ─→ README
```

**Parallel execution:** Waves 2, 3, and 4 can execute in parallel after Wave 1 completes (they share T1 dependency but are otherwise independent).

## Estimated Execution Time
- Wave 1 (T1): ~30 min
- Wave 2 (T2-T3): ~2.5 hours
- Wave 3 (T4-T5): ~2 hours
- Wave 4 (T6-T7): ~2.5 hours
- Wave 5 (T8): ~1.5 hours
- Wave 6 (T9-T10): ~2 hours
- Wave 7 (T11): ~30 min
- **Total:** ~11-12 hours (can be parallelized to ~8 hours with Waves 2-4 concurrent)

## Expected Output
- `src/context_memory_mcp/config.py` — `AutoConfig` dataclass with `load()`/`save()`, `get_config()` singleton
- `src/context_memory_mcp/auto_save.py` — `AutoSaveMiddleware` with buffer and ChromaDB flush
- `src/context_memory_mcp/auto_retrieve.py` — `ContextInjector` with query extraction and token budget
- `src/context_memory_mcp/file_watcher.py` — `FileWatcher` + `AutoTrackHandler` with debounce
- `src/context_memory_mcp/mcp_server.py` — Updated `run_server()` with wiring and `_wire_interception()`
- `tests/test_auto_save.py` — 7 tests for `AutoSaveMiddleware`
- `tests/test_auto_retrieve.py` — 6 tests for `ContextInjector`
- `tests/test_file_watcher.py` — 6 tests for `FileWatcher` (mocked Observer)
- `tests/test_auto_integration.py` — 4 end-to-end integration tests
- `README.md` — Updated with automatic feature documentation
- `./data/config.json` — Created with defaults
- `.planning/5-01-SUMMARY.md` — Execution summary with test results
- **11 atomic git commits** with `[GSD-5-01-T1]` through `[GSD-5-01-T11]` titles
