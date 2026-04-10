# Phase 6: Hybrid Context System & Auto-Retrieve Fix — Plan 01

## Wave 1: Fix Auto-Retrieve Root Cause

### T1: Fix query extraction in `_wire_interception` (CRITICAL BUG)
- **Description:** The `_intercepted_call_tool` function passes `query=name` (tool name like `"query_chat"`) instead of the actual user query from `arguments`. Implement `_extract_query_from_arguments()` helper and wire it into the interception call. This is the single most impactful fix — makes auto-retrieve work for the first time.
- **Files:** `src/context_memory_mcp/mcp_server.py`
- **Commit:** `[GSD-6-01-T1] fix query extraction in _wire_interception to use tool arguments`
- **Validation:**
  - `_extract_query_from_arguments()` exists and returns the most relevant string from arguments dict
  - Priority order: `query` > `conversation` > `search` > `text` > `content` > fallback join
  - `_context_injector.inject(query=user_query, ...)` uses extracted query, not tool name
  - Existing tests still pass (224 → 224+)

### T2: Verify monkey-patch interception still works after T1
- **Description:** Add an integration test that verifies the monkey-patch actually intercepts tool calls and passes real queries to the context injector (not tool names). Confirms T1 works end-to-end.
- **Files:** `tests/test_auto_e2e.py`
- **Commit:** `[GSD-6-01-T2] add integration test verifying monkey-patch query extraction`
- **Validation:**
  - Test stores chat messages, calls a tool via interception, verifies context block contains results matching the actual query content (not the tool name)
  - Test passes with `auto_retrieve=True` in config
  - Test is skipped if `auto_retrieve=False`

---

## Wave 2: Hybrid Context Builder Foundation

### T3: Implement `IntentClassifier` using sentence-transformers centroids
- **Description:** Create a new `IntentClassifier` class that pre-computes intent centroid embeddings at startup and classifies queries via cosine similarity. Returns `"chat"`, `"file"`, `"both"`, or `"unknown"`. Uses existing `SentenceTransformerEmbeddingFunction` — zero new dependencies.
- **Files:** `src/context_memory_mcp/intent_classifier.py` (NEW), `src/context_memory_mcp/embeddings.py`
- **Commit:** `[GSD-6-01-T3] implement IntentClassifier with pre-computed intent centroids`
- **Validation:**
  - `IntentClassifier.__init__` pre-computes chat and file centroids (~8 embeddings total)
  - `classify(query)` returns one of `"chat"`, `"file"`, `"both"`, `"unknown"`
  - Cosine similarity uses numpy (transitive dependency, no install needed)
  - Unit tests: known chat queries → `"chat"`, known file queries → `"file"`, ambiguous → `"both"`
  - Classification latency <100ms per query
  - At least 8 new tests for classifier

### T4: Extend `ChatStore` with `store_file_change()` and type-aware queries
- **Description:** Add `store_file_change()` method to store file change documents in the same ChromaDB collection with `type="file_change"` metadata. Update `_build_where()` to support `type` filtering. Treat missing `type` as `"chat"` for backward compatibility.
- **Files:** `src/context_memory_mcp/chat_store.py`
- **Commit:** `[GSD-6-01-T4] add store_file_change and type-aware query support to ChatStore`
- **Validation:**
  - `store_file_change(file_change: dict, session_id=None)` stores document with `type="file_change"` metadata
  - Document format: `"{change_type} {file_path}: {snippet}"`
  - Metadata includes: `type`, `file_path`, `change_type`, `symbols`, `timestamp`
  - `_build_where()` accepts optional `doc_type` parameter
  - `query_messages()` treats missing `type` as `"chat"` (backward compatible)
  - At least 6 new tests for file change storage and type filtering

### T5: Rewrite `HybridContextBuilder` replacing stub `ContextBuilder.build()`
- **Description:** Replace the stub `ContextBuilder.build()` with `HybridContextBuilder` that uses `IntentClassifier` to route queries. Queries ChromaDB for chat/file changes based on intent. **Does NOT include FileGraph structural queries yet** — that's T11. This task focuses on ChromaDB dual-source routing only.
- **Files:** `src/context_memory_mcp/context.py`
- **Commit:** `[GSD-6-01-T5] rewrite ContextBuilder as HybridContextBuilder with intent routing`
- **Validation:**
  - `HybridContextBuilder.__init__` accepts `ChatStore`, optional `FileGraph`, `IntentClassifier`
  - `build(query, session_id, active_files)` classifies intent and routes accordingly
  - Chat intent → queries ChromaDB with `type="chat"` filter
  - File intent → queries ChromaDB with `type="file_change"` filter (FileGraph skipped for now)
  - Both intent → queries both ChromaDB sources, merges results (FileGraph skipped for now)
  - Token budget enforced (split: 60% chat, 40% file, adjustable)
  - `ContextWindow.sources` populated with `["chat_history"]`, `["file_changes"]` as applicable
  - Existing `format_with_detail()` and `_estimate_tokens()` reused
  - At least 10 new tests for hybrid builder (ChromaDB-only at this stage)

### T6: Update `ContextInjector` to use `HybridContextBuilder` with dual injection
- **Description:** Modify `ContextInjector` to delegate to `HybridContextBuilder` instead of directly querying ChromaDB. **Implement dual injection:** (1) Format context as structured system-prompt-like prefix (e.g., `[SYSTEM CONTEXT: ...]`) for the response prepend, and (2) keep the existing append fallback. This fulfills 6-CONTEXT.md Decision 1.
- **Files:** `src/context_memory_mcp/auto_retrieve.py`
- **Commit:** `[GSD-6-01-T6] update ContextInjector with dual injection (system prompt + response append)`
- **Validation:**
  - `ContextInjector.__init__` accepts `HybridContextBuilder` (or creates one from store/graph/classifier)
  - `inject()` calls `builder.build()` instead of `store.query_messages()` directly
  - Returns dual-format context: `[SYSTEM CONTEXT: ...]\n{content}\n[Sources: ...]`
  - Format looks like a system instruction so LLM naturally uses it
  - Returns empty string when disabled or no context found
  - Token budget still enforced via `HybridContextBuilder`
  - At least 4 new tests for updated injector

### T7: Wire `IntentClassifier` and `HybridContextBuilder` into `_wire_interception`
- **Description:** Update `_wire_interception()` in `mcp_server.py` to create and use `IntentClassifier` and `HybridContextBuilder` singletons. Ensure `ContextInjector` is initialized with the hybrid builder.
- **Files:** `src/context_memory_mcp/mcp_server.py`
- **Commit:** `[GSD-6-01-T7] wire IntentClassifier and HybridContextBuilder into mcp_server`
- **Validation:**
  - `IntentClassifier` instantiated once at wiring time (centroids pre-computed)
  - `HybridContextBuilder` instantiated with store, graph, classifier
  - `ContextInjector` receives hybrid builder
  - No regression: existing tools still work
  - Module-level globals updated: `_intent_classifier`, `_context_builder`
  - Follows existing singleton pattern (`get_store()`, `get_graph()`)

---

## Wave 3: File Change History Tracking

### T8: Add file change logging hooks to `FileGraph.update_graph()`
- **Description:** When `FileGraph.update_graph()` processes changed files, capture change metadata (change_type, symbols added/removed, code snippet) and store it via `ChatStore.store_file_change()`. Hook into the existing update flow without breaking current behavior.
- **Files:** `src/context_memory_mcp/file_graph.py`, `src/context_memory_mcp/chat_store.py`
- **Commit:** `[GSD-6-01-T8] add file change logging hooks to FileGraph update_graph`
- **Validation:**
  - `update_graph()` calls `store_file_change()` for each changed file
  - Change metadata includes: `file_path`, `change_type` (modified/created/deleted), `symbols_added`, `symbols_removed`, `snippet` (truncated to 200 chars), `timestamp`
  - Deleted files: `change_type="deleted"`, no snippet
  - New files: `change_type="created"`
  - Existing files with hash mismatch: `change_type="modified"`
  - Hook is optional — doesn't break if store is unavailable
  - At least 4 new tests for change logging hooks

### T9: Add file change logging hooks to `FileWatcher`
- **Description:** Hook into `FileWatcher.on_modified`, `on_created`, `on_deleted` callbacks to store file change documents in ChromaDB. The FileWatcher already calls `graph.update_graph()` — we additionally store the change event directly for real-time tracking.
- **Files:** `src/context_memory_mcp/file_watcher.py`
- **Commit:** `[GSD-6-01-T9] add file change logging hooks to FileWatcher callbacks`
- **Validation:**
  - `FileWatcher.__init__` accepts optional `ChatStore` parameter
  - `on_modified`, `on_created`, `on_deleted` call `store_file_change()` with appropriate metadata
  - Debounce logic preserved (Windows OneDrive safety)
  - Hook is optional — watcher works without store (backward compatible)
  - At least 4 new tests for watcher file change logging

### T10: Add `query_file_changes()` method to `ChatStore`
- **Description:** Add a dedicated method for querying file change documents from ChromaDB. Supports filtering by date range, file path, and change type. Returns structured results with change metadata.
- **Files:** `src/context_memory_mcp/chat_store.py`
- **Commit:** `[GSD-6-01-T10] add query_file_changes method to ChatStore`
- **Validation:**
  - `query_file_changes(query, top_k, date_from, date_to, file_path, change_type)` exists
  - Uses `where={"type": "file_change"}` filter
  - Optional `file_path` filter: `where={"type": "file_change", "file_path": path}`
  - Optional `change_type` filter
  - Date filtering in Python (existing pattern)
  - Returns list of dicts with `content`, `file_path`, `change_type`, `symbols`, `timestamp`, `distance`, `similarity`
  - At least 6 new tests for file change queries

---

## Wave 4: Hybrid Auto-Retrieve Integration

### T11: Add FileGraph structural queries to `HybridContextBuilder`
- **Description:** Extend `HybridContextBuilder.build()` (from T5) to also query FileGraph when intent is `"file"` or `"both"`. Extract file paths from query text, query graph for dependencies/dependents, merge with ChromaDB results. This completes the full hybrid picture.
- **Files:** `src/context_memory_mcp/context.py`
- **Commit:** `[GSD-6-01-T11] add FileGraph structural queries to HybridContextBuilder`
- **Validation:**
  - When `active_files` provided or file paths detected in query, queries `file_graph.get_dependencies(f)` for each file
  - Queries `file_graph.get_dependents(f)` for each file
  - Formats output: `"Dependencies of {file}: {list}"`, `"Dependents of {file}: {list}"`
  - Token budget enforced — truncates if over 40% file budget
  - Graceful degradation: if FileGraph empty or file not found, skips without error
  - `_extract_file_paths(query)` helper attempts to find file paths in query text
  - `ContextWindow.sources` now includes `"file_graph"` when graph data present
  - At least 6 new tests for FileGraph integration

### T12: Update `get_context` MCP tool to use `HybridContextBuilder`
- **Description:** The `get_context` tool in `context.py` currently uses the stub `ContextBuilder`. Update it to use `HybridContextBuilder` with actual hybrid retrieval. The tool should accept the same parameters but return enriched results from both ChromaDB and FileGraph.
- **Files:** `src/context_memory_mcp/context.py`
- **Commit:** `[GSD-6-01-T12] update get_context tool to use HybridContextBuilder`
- **Validation:**
  - `register(mcp)` creates `HybridContextBuilder` with store, graph, classifier
  - `get_context` tool returns JSON with `sources` array (e.g., `["chat_history", "file_changes", "file_graph"]`)
  - `content` field contains merged hybrid context
  - `token_count` reflects actual merged content
  - Works with `detail_level` parameter (minimal, summary, full)
  - At least 4 new tests for updated get_context tool

---

## Wave 5: Testing & Verification

### T13: Add comprehensive tests for `IntentClassifier`
- **Description:** Unit tests covering all classification scenarios: clear chat intent, clear file intent, ambiguous queries (both), unknown/edge cases, centroid pre-computation, and cosine similarity correctness.
- **Files:** `tests/test_intent_classifier.py` (NEW)
- **Commit:** `[GSD-6-01-T13] add comprehensive tests for IntentClassifier`
- **Validation:**
  - At least 12 tests covering:
    - Chat queries classified as `"chat"` (e.g., "what did we discuss", "remember what I said")
    - File queries classified as `"file"` (e.g., "which files changed", "import dependencies")
    - Mixed queries classified as `"both"` (e.g., "what did we say about the file changes")
    - Empty query → `"both"` (safe fallback)
    - Centroids pre-computed once at init (not per-query)
    - Classification is deterministic for same input
    - Cosine similarity produces correct values
  - All tests use `tmp_path` for isolation

### T14: Add comprehensive tests for hybrid `ChatStore` file changes
- **Description:** Tests for `store_file_change()`, `query_file_changes()`, type-aware `_build_where()`, and backward compatibility with existing messages lacking `type` metadata.
- **Files:** `tests/test_chat_store.py` (MODIFY)
- **Commit:** `[GSD-6-01-T14] add tests for ChatStore file change storage and queries`
- **Validation:**
  - At least 10 tests covering:
    - `store_file_change()` stores with correct metadata
    - `query_file_changes()` returns only file_change documents
    - `query_messages()` with `type="chat"` excludes file changes
    - Backward compatibility: messages without `type` treated as chat
    - Date filtering on file changes
    - File path filtering on file changes
    - Change type filtering (modified/created/deleted)
    - Empty file changes collection returns empty list
    - Token budget not exceeded in query results
  - All existing 191+ tests still pass

### T15: Add end-to-end integration tests for hybrid context system
- **Description:** Integration tests that verify the full hybrid retrieval pipeline: query → intent classification → ChromaDB + FileGraph → merged context → injection. Tests the complete flow from `get_context` tool call through to context injection in tool responses.
- **Files:** `tests/test_integration.py` (MODIFY)
- **Commit:** `[GSD-6-01-T15] add end-to-end integration tests for hybrid context system`
- **Validation:**
  - At least 8 tests covering:
    - Chat-only query returns chat context with `sources=["chat_history"]`
    - File-only query returns file context with `sources=["file_changes", "file_graph"]`
    - Mixed query returns combined context with multiple sources
    - Auto-retrieve via monkey-patch injects hybrid context (not just tool name)
    - Empty database returns empty context gracefully
    - FileGraph integration returns dependency information
    - Token budget enforced across merged sources
    - Full pipeline: store messages → store file changes → query → verify hybrid results
  - All existing integration tests still pass

### T16: Update README with Phase 6 hybrid context documentation
- **Description:** Update README.md to document the hybrid context system, intent classification, file change tracking, and auto-retrieve behavior. Include examples of how the system works end-to-end.
- **Files:** `README.md`
- **Commit:** `[GSD-6-01-T16] update README with Phase 6 hybrid context documentation`
- **Validation:**
  - Documents `IntentClassifier` and semantic intent detection
  - Documents file change storage in ChromaDB (unified collection)
  - Documents `HybridContextBuilder` routing logic
  - Documents auto-retrieve fix (query extraction from tool arguments)
  - Includes example queries showing chat vs file vs both routing
  - Updates tool list if any new tools added
  - README line count increases (additions, not replacements)

---

## Wave Summary

| Wave | Tasks | Focus | Risk | Est. Time |
|------|-------|-------|------|-----------|
| **1: Fix Auto-Retrieve** | T1–T2 | Critical bug fix + verification | Low | 1 hour |
| **2: Hybrid Context Builder** | T3–T7 | Intent classifier, ChromaDB type support, hybrid builder, wiring | Medium | 4-5 hours |
| **3: File Change History** | T8–T10 | FileGraph hooks, FileWatcher hooks, query method | Low | 2-3 hours |
| **4: Hybrid Integration** | T11–T12 | FileGraph structural queries, get_context tool update | Medium | 1-2 hours |
| **5: Testing & Verification** | T13–T16 | Comprehensive tests + README | Low | 2-3 hours |

### Totals
- **Tasks:** 16
- **New files:** 2 (`intent_classifier.py`, `test_intent_classifier.py`)
- **Modified files:** 8 (`mcp_server.py`, `auto_retrieve.py`, `chat_store.py`, `context.py`, `file_graph.py`, `file_watcher.py`, `test_chat_store.py`, `test_integration.py`, `test_auto_e2e.py`, `README.md`)
- **Expected test count:** 280+ (224 existing + ~56 new)
- **New dependencies:** 0 (uses existing sentence-transformers, chromadb, networkx, numpy)

---

## Dependency Graph

```
Wave 1: T1 ──→ T2
              ↓
Wave 2: T3 ──→ T5 ──→ T6 ──→ T7
         T4 ──→ T5           ↑
Wave 3: T8 ──→ T11
         T9
         T10 (independent)
Wave 4: T11 ──→ T12
Wave 5: T13 (depends on T3)
         T14 (depends on T4, T10)
         T15 (depends on T5, T6, T7, T8, T11, T12)
         T16 (independent, documentation)
```

### Critical Path
T1 → T2 (verify fix) → T3 + T4 (parallel) → T5 → T6 → T7 → T8 → T11 → T12 → T15

### Parallel Opportunities
- T3 and T4 can execute in parallel (independent modules)
- T8, T9, T10 can execute in parallel (all add file change support)
- T13, T14, T16 can execute in parallel (testing independent components)
- T15 must execute last (depends on all integration points)

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| Intent classifier misclassifies | Use `"both"` as safe fallback; tune centroids in tests |
| ChromaDB Windows file locks | Ensure `close()` in test teardown; use `tmp_path` isolation |
| Existing tests break from `type` metadata | Treat missing `type` as `"chat"` in `_build_where()` |
| Monkey-patch breaks after T1 changes | T2 integration test verifies interception works |
| Token budget exceeded in hybrid merge | `ContextWindow.fits()` check before each section addition |
| FileGraph empty during integration tests | Graceful degradation — skip FileGraph, return ChromaDB only |

---

## Research References
- **6-RESEARCH.md:** FastMCP system prompt injection approaches, semantic intent classification, ChromaDB single-collection pattern, FileGraph integration strategies
- **6-CONTEXT.md:** Dual context injection decision, semantic query classification, unified ChromaDB storage, full tracking granularity
- **STATE.md:** Current position — PHASE_6_PLANNED, awaiting user approval
