# Phase 2 Plan — 2-01

## Objective
Implement full chat history persistence with ChromaDB, local embeddings, and MCP tools (`store_chat`, `query_chat`) for storing and querying conversation history. This completes the MVP.

## Context
- **Research:** `.planning/2-RESEARCH.md` — ChromaDB v1.5.7 API, embedding integration, metadata filtering limitations, Windows file lock issues, FastMCP tool registration patterns
- **Decisions:** `.planning/2-CONTEXT.md` — `PersistentClient`, built-in `SentenceTransformerEmbeddingFunction`, batch `store_chat`, full-filter `query_chat`, auto-generate UUID, `./data/chromadb` path, errors bubble up
- **Current state:** `chat_store.py` has placeholder classes with `...` bodies — needs full replacement. `mcp_server.py` has commented-out import for chat_store registration. `tests/` is empty.

---

## Wave 1: Core Implementation

| Task | Description | Requirement | Commit Title |
|------|-------------|-------------|--------------|
| T1 | Implement `ChatStore.__init__` — Create `PersistentClient(path="./data/chromadb")`, `SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")`, and `get_or_create_collection(name="chat_history", ...)` with `{"hnsw:space": "cosine"}` metadata. Add `close()` method that calls `self._client.close()`. | FR-1, FR-2 | `[GSD-2-01-T1] implement ChatStore init with PersistentClient and embedding function` |
| T2 | Implement `ChatStore.store_messages(messages, session_id=None)` — Auto-generate `uuid4` if `session_id` is `None`. For each message, extract `content` as document, build metadata `{"session_id": ..., "role": ..., "timestamp": ...}` (use `datetime.now(timezone.utc).isoformat()` as fallback timestamp). Generate `uuid4` per document ID. Call `collection.add(ids=ids, documents=docs, metadatas=metas)`. Return `{"stored": count, "session_id": session_id}`. | FR-3 | `[GSD-2-01-T2] implement batch store_messages with auto session UUID generation` |
| T3 | Implement `ChatStore._build_where(session_id=None, role=None)` helper — Returns `None` if no filters, single dict if one filter, or `{"$and": [cond1, cond2]}` if both. This is used by `query_messages` for ChromaDB `where` clauses. | FR-4 | `[GSD-2-01-T3] add _build_where helper for ChromaDB where clause construction` |
| T4 | Implement `ChatStore.query_messages(query, top_k=5, session_id=None, date_from=None, date_to=None, role=None)` — Build where clause via `_build_where`. Query ChromaDB with `n_results=max(top_k * 3, 50)` (over-fetch for date filtering). Access double-nested results via `[0]` index. Apply date filtering in Python via ISO 8601 string comparison (`ts < date_from`, `ts > date_from`). Build result dicts with `content`, `role`, `timestamp`, `session_id`, `distance`, `similarity` (1 - distance). Slice to `top_k`. | FR-4, FR-5 | `[GSD-2-01-T4] implement query_messages with semantic search and Python date filtering` |
| T5 | Implement `ChatStore.list_sessions()` — Call `collection.get(include=["metadatas"])`. Extract unique `session_id` values from metadata. Return sorted list of distinct session IDs. | FR-6 | `[GSD-2-01-T5] implement list_sessions via ChromaDB get and metadata dedup` |
| T6 | Implement `ChatStore.delete_session(session_id)` — Call `collection.get(where={"session_id": session_id}, include=["ids"])` to get document IDs, then `collection.delete(ids=...)`. Return count of deleted messages. | FR-7 | `[GSD-2-01-T6] implement delete_session via where-filter get then delete` |
| T7 | Add `register(mcp: FastMCP)` function in `chat_store.py` — Define `store_chat` tool (batch ingestion with `Annotated[list[dict[str, str]], Field(...)]` and `Annotated[str \| None, Field(...)]`) and `query_chat` tool (with `query`, `top_k`, `session_id`, `date_from`, `date_to`, `role` params). Both return `json.dumps(...)` of their results. Instantiate a module-level `ChatStore` singleton. | FR-3, FR-4 | `[GSD-2-01-T7] add register function with store_chat and query_chat MCP tools` |
| T8 | Update `mcp_server.py` `register_all()` — Uncomment the Phase 2 import line and add `register_chat(mcp)` call. | FR-3, FR-4 | `[GSD-2-01-T8] wire up chat_store registration in mcp_server register_all` |

## Wave 2: Tests (depends on Wave 1)

| Task | Description | Requirement | Commit Title |
|------|-------------|-------------|--------------|
| T9 | Create `tests/test_chat_store.py` — Write pytest tests: (a) `test_store_and_query` — store messages, query by semantic similarity, verify results contain expected content; (b) `test_session_isolation` — store in session A, query session B, verify no cross-contamination; (c) `test_date_filtering` — store messages with different timestamps, query with `date_from`/`date_to`, verify Python date filtering works; (d) `test_role_filter` — query with `role="user"`, verify only user messages returned; (e) `test_list_sessions` — verify distinct session IDs; (f) `test_delete_session` — verify messages removed; (g) `test_auto_session_id` — verify UUID auto-generation. Use `tmp_path` fixture for ChromaDB path to ensure test isolation. Call `store.close()` in teardown. | FR-1 through FR-7 | `[GSD-2-01-T9] add pytest tests for ChatStore CRUD, filtering, and session isolation` |

## Wave 3: End-to-End Verification (depends on Wave 2)

| Task | Description | Requirement | Commit Title |
|------|-------------|-------------|--------------|
| T10 | Run full test suite with `pytest tests/test_chat_store.py -v`. Verify all tests pass. Start the MCP server via `python -m context_memory_mcp` and verify it starts without errors (model download may take ~25s on first run). Confirm `./data/chromadb` directory is created. Create `2-01-SUMMARY.md` documenting execution results, any deviations, and test outcomes. | FR-1 through FR-7, MVP | `[GSD-2-01-T10] run tests, verify server starts, create 2-01-SUMMARY.md` |

---

## Verification

### Wave 1 Verification
- [ ] T1: `ChatStore` initializes without error, `./data/chromadb` directory is created, `close()` runs without exception
- [ ] T2: `store_messages` returns correct `{"stored": N, "session_id": "..."}` dict; messages appear in ChromaDB collection
- [ ] T3: `_build_where` returns `None` (no filters), `{"role": "user"}` (one filter), `{"$and": [...]}` (two filters)
- [ ] T4: `query_messages` returns list of dicts with correct keys; date filtering excludes out-of-range results; `top_k` limits output
- [ ] T5: `list_sessions` returns sorted list of unique session IDs
- [ ] T6: `delete_session` removes all messages for a session and returns correct count
- [ ] T7: `register(mcp)` registers both `store_chat` and `query_chat` tools with correct parameter types and descriptions
- [ ] T8: `register_all()` imports and calls `register_chat(mcp)` without error

### Wave 2 Verification
- [ ] T9: All 7+ test functions pass with `pytest tests/test_chat_store.py -v`

### Wave 3 Verification
- [ ] T10: Full test suite passes; server starts without crash; `./data/chromadb` exists; `2-01-SUMMARY.md` created

## Dependencies
- **Wave 1** → no dependencies (can start immediately)
- **Wave 2** → depends on Wave 1 (tests need implemented code)
- **Wave 3** → depends on Wave 2 (verification needs passing tests)

## Estimated Execution Time
- Wave 1: ~2-3 hours (implementation)
- Wave 2: ~1 hour (test writing)
- Wave 3: ~15 minutes (verification + summary)
- **Total:** ~3-4.5 hours

## Expected Output
- `src/context_memory_mcp/chat_store.py` — Full `ChatStore` implementation with `register()` function
- `src/context_memory_mcp/mcp_server.py` — Updated `register_all()` with chat_store wiring
- `tests/test_chat_store.py` — Comprehensive pytest test suite
- `.planning/2-01-SUMMARY.md` — Execution summary with test results and any deviations
- 10 atomic git commits with `[GSD-2-01-T1]` through `[GSD-2-01-T10]` titles
