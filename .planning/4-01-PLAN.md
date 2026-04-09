---
phase: 4
plan: 01
type: feature
wave: 1
depends_on: []
---

## Objective
Implement token-efficient context retrieval, detail-level formatting, fix 4 deferred MAJOR items from Phases 2/3, enhance `query_chat` filters, add integration tests, and write comprehensive README. This is the **final phase** — project complete after this.

## Context
- Phase 1, 2, and 3 are **COMPLETE and SHIPPED** (99 tests passing)
- Placeholder exists at `src/context_memory_mcp/context.py` with `ContextWindow` and `ContextBuilder` stubs
- MCP tool registration follows `register(mcp: FastMCP)` pattern
- Project uses `src/context_memory_mcp/` package layout
- Environment: Windows, Python 3.13.7, pip-based venv
- 4-CONTEXT.md decisions guide all implementation choices
- MAJOR fixes deferred from Phases 2/3 must be completed here

---

## Wave 1: Foundation & Context System (Tasks 1–4)
*No external dependencies. Can execute immediately.*

### Task 1: Implement `get_minimal_context()` — token compression to ~100 tokens
**Type:** auto
**Dependencies:** none
**Estimated effort:** 30 min
**Commit scope:** `src/context_memory_mcp/context.py` — add `get_minimal_context()` function + token estimation

**Description:**
Implement the hybrid template + smart truncation function that compresses query_chat results to fit ~100 token budget. Per 4-CONTEXT.md Decision 1:
- Input: list of message dicts from `query_messages()`
- Strategy: Extract key info only — most recent user query, 1-2 recent assistant replies, active file count
- Token estimation: Use 4 chars/token heuristic (Decision 2 rationale)
- Truncation: Cut content at token boundary, append `...` if truncated
- Return: `ContextWindow` instance with compressed content

**Success criteria:**
- [ ] `get_minimal_context(messages)` returns a `ContextWindow` with `token_count <= ~120`
- [ ] Token estimation uses `len(text) // 4` heuristic
- [ ] Truncation preserves message structure (role + content pairs)
- [ ] Handles empty input gracefully (returns empty ContextWindow)
- [ ] Handles single message, many messages, oversized messages
- [ ] Unit test: `test_get_minimal_context_fits_budget()` passes

---

### Task 2: Implement `format_with_detail()` — minimal/summary/full modes
**Type:** auto
**Dependencies:** Task 1
**Estimated effort:** 25 min
**Commit scope:** `src/context_memory_mcp/context.py` — add `format_with_detail()` function

**Description:**
Implement detail-level formatting per 4-CONTEXT.md Decision 2:
- `minimal` (~100 tokens): Key info only — last query, last reply, file counts
- `summary` (~300 tokens): Adds recent message headers, active file list, semantic match highlights
- `full`: Raw message results, no truncation
- Input: query results + detail level enum
- Output: Formatted string ready for MCP tool response
- Token estimation: Same 4 chars/token heuristic

**Success criteria:**
- [ ] `format_with_detail(results, level="minimal")` returns ~100 token output
- [ ] `format_with_detail(results, level="summary")` returns ~300 token output
- [ ] `format_with_detail(results, level="full")` returns all raw data
- [ ] Invalid level raises `ValueError`
- [ ] Empty results handled gracefully
- [ ] Unit test: `test_format_with_detail_all_levels()` passes

---

### Task 3: Implement `ContextBuilder.build()` and register `get_context` MCP tool
**Type:** auto
**Dependencies:** Tasks 1, 2
**Estimated effort:** 30 min
**Commit scope:** `src/context_memory_mcp/context.py` — complete `ContextBuilder` + `register()` function; `src/context_memory_mcp/mcp_server.py` — uncomment context registration

**Description:**
Complete the `ContextBuilder` class to assemble context windows from multiple sources:
- `build(query, session_id, active_files)` — orchestrates recent messages + file context
- Uses `get_minimal_context()` internally for compression
- `register(mcp: FastMCP)` — registers `get_context` MCP tool with parameters:
  - `query`: search query
  - `session_id`: optional session filter
  - `detail_level`: "minimal" | "summary" | "full" (default: "summary")
  - `active_files`: optional list of file paths
- Uncomment registration in `mcp_server.py` `register_all()` function

**Success criteria:**
- [ ] `ContextBuilder.build()` returns a `ContextWindow` with content, sources, token_count
- [ ] `get_context` MCP tool registered and callable
- [ ] Tool accepts all 4 parameters with correct types and defaults
- [ ] `mcp_server.py` imports and calls `register_context(mcp)` in `register_all()`
- [ ] Manual test: `get_context(query="test")` returns valid JSON response
- [ ] `uv run python -c "from context_memory_mcp.context import register; print('OK')"` succeeds

---

### Task 4: `prune_sessions()` method + max_sessions config in ChatStore
**Type:** auto
**Dependencies:** none (MAJOR #1 fix — independent)
**Estimated effort:** 25 min
**Commit scope:** `src/context_memory_mcp/chat_store.py` — add `prune_sessions()` method

**Description:**
Implement session pruning per 4-CONTEXT.md § Prune Strategy:
```python
def prune_sessions(
    self,
    before_date: str | None = None,
    max_sessions: int | None = None,
) -> dict:
    """Remove old sessions to control collection size."""
```
- Option A: Delete all sessions with `last_message < before_date`
- Option B: Keep only N most recent sessions, delete rest
- Both options can be combined (date filter then cap)
- Returns: `{"pruned": count, "remaining": count}`
- Must update session index if it exists (Task 5)
- Must NOT break existing `list_sessions()`, `delete_session()` behavior

**Success criteria:**
- [ ] `prune_sessions(before_date="2024-01-01T00:00:00+00:00")` deletes old sessions
- [ ] `prune_sessions(max_sessions=5)` keeps only 5 most recent
- [ ] Combined call: date filter applied first, then cap
- [ ] Returns correct `pruned` and `remaining` counts
- [ ] No error when no sessions to prune (returns `{"pruned": 0, "remaining": N}`)
- [ ] Existing `list_sessions()` reflects pruned state
- [ ] Unit test: `test_prune_sessions_by_date()` passes
- [ ] Unit test: `test_prune_sessions_by_max()` passes

---

## Wave 2: Performance Optimizations (Tasks 5–7)
*Depends on Wave 1 for session index awareness. Tasks 5, 6, 7 can run in parallel.*

### Task 5: Session index JSON — optimize `list_sessions()` to O(1)
**Type:** auto
**Dependencies:** Task 4 (prune may affect index)
**Estimated effort:** 35 min
**Commit scope:** `src/context_memory_mcp/chat_store.py` — add session index management; `data/session_index.json` — new file (auto-created)

**Description:**
Eliminate O(n) `list_sessions()` per 4-CONTEXT.md § Session Index:
- Create `./data/session_index.json` structure:
```json
{
  "sessions": {
    "session-uuid-1": {
      "message_count": 42,
      "first_message": "ISO-8601",
      "last_message": "ISO-8601"
    }
  },
  "updated_at": "ISO-8601"
}
```
- Update index atomically on every `store_messages()` call
- Update index on `delete_session()` call
- Update index on `prune_sessions()` call (Task 4)
- `list_sessions()` reads index keys instead of fetching entire ChromaDB collection
- Index loaded lazily on first access, cached in memory
- Index file created automatically if missing (rebuild from ChromaDB)

**Success criteria:**
- [ ] `list_sessions()` returns session IDs from index (not ChromaDB query)
- [ ] `store_messages()` updates index with new session metadata
- [ ] `delete_session()` removes session from index
- [ ] `prune_sessions()` updates index after deletion
- [ ] Index file created at `./data/session_index.json` on first store
- [ ] Index rebuilds from ChromaDB if file missing but data exists
- [ ] `list_sessions()` returns sorted list (alphabetical)
- [ ] Unit test: `test_session_index_updated_on_store()` passes
- [ ] Unit test: `test_session_index_updated_on_delete()` passes
- [ ] Unit test: `test_list_sessions_reads_index()` passes

---

### Task 6: Fix import matching — parse AST nodes not substring match
**Type:** auto
**Dependencies:** none (MAJOR #3 fix — independent)
**Estimated effort:** 30 min
**Commit scope:** `src/context_memory_mcp/parser.py` — rewrite `extract_imports_edges()` to use AST node parsing

**Description:**
Fix fragile import matching per 4-CONTEXT.md Decision 3 (MAJOR #3):
- **Current problem:** `extract_imports_edges()` does substring matching on import text (e.g., `"import os"` matched against `"os.py"`)
- **Fix:** Parse the import AST node to extract the actual module name
- For Python `import X` → module name is `X`
- For `from X import Y` → module name is `X`
- For `from X.Y import Z` → module name is `X.Y` (check both `X` and `X.Y`)
- Match module names to known files by:
  1. Direct module-to-file name match (`os` → `os.py`)
  2. Package path match (`os.path` → `os/path.py` or `os/path/__init__.py`)
- Update `ParsedSymbol` for imports to store parsed module name (not raw text)
- Add `_parse_import_module(import_text: str) -> str` helper

**Success criteria:**
- [ ] `import os` correctly matches `os.py` (not `some_os_helper.py`)
- [ ] `from collections import OrderedDict` matches `collections.py` or `collections/__init__.py`
- [ ] `from os.path import join` matches `os/path.py`
- [ ] `import context_memory_mcp.chat_store` matches `chat_store.py`
- [ ] No false positives from substring overlap (e.g., `test_chat_store` doesn't match `chat_store.py` unless actual import)
- [ ] `extract_imports_edges()` uses parsed module names, not raw text
- [ ] Existing tests still pass (no regressions)
- [ ] Unit test: `test_import_matching_uses_ast_nodes()` passes

---

### Task 7: Fix double-parsing in `update_graph`
**Type:** auto
**Dependencies:** none (MAJOR #4 fix — independent)
**Estimated effort:** 20 min
**Commit scope:** `src/context_memory_mcp/file_graph.py` — refactor `update_graph()` to reuse first-pass symbols

**Description:**
Eliminate double-parsing per 4-CONTEXT.md Decision 3 (MAJOR #4):
- **Current problem:** `update_graph()` calls `self._parser.parse_file(f)` twice per changed file:
  1. First pass (line ~340) — extracts symbols for node creation
  2. Second pass (line ~380) — re-parses same file for edge extraction
- **Fix:** Store symbols from first pass in a dict, reuse for edge extraction
- Retain `all_symbols` dict (already exists in `build_graph()`) for reuse
- No change to correctness — same edges produced, just one parse per file

**Success criteria:**
- [ ] `update_graph()` calls `parse_file()` exactly once per changed file
- [ ] Same edges produced as before (no regression)
- [ ] Performance improvement measurable (fewer parse calls)
- [ ] `build_graph()` unaffected (already uses single-pass pattern)
- [ ] Existing `test_file_graph.py` tests still pass
- [ ] Unit test: `test_update_graph_no_double_parse()` passes (verify via mock)

---

## Wave 3: Query Enhancement & Testing (Tasks 8–11)
*Depends on Wave 1 (context system) and Wave 2 (session index).*

### Task 8: `conversation_id` filter on `query_chat` — re-implement with validation
**Type:** auto
**Dependencies:** none
**Estimated effort:** 20 min
**Commit scope:** `src/context_memory_mcp/chat_store.py` — update `register()` tool; `query_messages()` parameter handling

**Description:**
Enhance `query_chat` MCP tool per 4-CONTEXT.md Decision 4:
- Add `conversation_id` parameter as alias for `session_id`
- If both provided, `conversation_id` takes precedence (log warning)
- Input validation: reject empty strings, validate format (UUID-like or string)
- Edge case: empty results return `[]` not error
- Update MCP tool schema to document `conversation_id` parameter
- Ensure backward compatibility — existing `session_id` usage unchanged

**Success criteria:**
- [ ] `query_chat(conversation_id="sess-123")` works same as `session_id="sess-123"`
- [ ] Both params provided → `conversation_id` used, warning logged
- [ ] Empty string `conversation_id=""` raises `ValueError`
- [ ] Results return `[]` for non-existent session (not error)
- [ ] MCP tool schema documents both parameters
- [ ] Unit test: `test_query_chat_conversation_id_alias()` passes
- [ ] Unit test: `test_query_chat_empty_conversation_id_raises()` passes

---

### Task 9: Date range filter on `query_chat` — re-implement with validation
**Type:** auto
**Dependencies:** none
**Estimated effort:** 25 min
**Commit scope:** `src/context_memory_mcp/chat_store.py` — enhance `query_messages()` date validation

**Description:**
Enhance date range filtering per 4-CONTEXT.md Decision 4:
- Validate `date_from` and `date_to` are ISO 8601 format
- Reject invalid date strings with clear error message
- Handle `date_from > date_to` gracefully (swap or error)
- Edge case: empty results return `[]` not error
- Edge case: conflicting date ranges handled (no messages match → `[]`)
- Ensure existing date filtering tests still pass (from Task 4.13 in Phase 2)

**Success criteria:**
- [ ] `query_messages(date_from="2024-01-01")` works (enforces ISO 8601)
- [ ] Invalid date `date_from="not-a-date"` raises `ValueError`
- [ ] `date_from > date_to` → swap automatically (log warning) or raise error
- [ ] Empty results return `[]` (not error)
- [ ] Existing date filtering tests still pass
- [ ] Unit test: `test_query_chat_invalid_date_raises()` passes
- [ ] Unit test: `test_query_chat_date_range_swap()` passes

---

### Task 10: Unit tests for chat_store — prune, index, validation
**Type:** auto
**Dependencies:** Tasks 4, 5, 8, 9
**Estimated effort:** 30 min
**Commit scope:** `tests/test_chat_store.py` — add new test functions

**Description:**
Add comprehensive tests for Phase 4 chat_store features:
- `test_prune_sessions_by_date()` — verify date-based pruning
- `test_prune_sessions_by_max()` — verify max_sessions cap
- `test_prune_sessions_combined()` — date + max combined
- `test_session_index_updated_on_store()` — index creation/update
- `test_session_index_updated_on_delete()` — index cleanup
- `test_session_index_rebuild_on_missing()` — auto-rebuild from ChromaDB
- `test_list_sessions_reads_index()` — O(1) behavior verified
- `test_query_chat_conversation_id_alias()` — alias behavior
- `test_query_chat_empty_conversation_id_raises()` — validation
- `test_query_chat_invalid_date_raises()` — date validation
- `test_query_chat_date_range_swap()` — edge case handling

**Success criteria:**
- [ ] All 11 new tests pass
- [ ] Tests use `tmp_path` fixture for isolation
- [ ] Tests cover edge cases (empty, invalid, boundary conditions)
- [ ] Total test count increases from 99 to 110+
- [ ] `pytest tests/test_chat_store.py -v` passes

---

### Task 11: Unit tests for file_graph — import matching, double-parse fix
**Type:** auto
**Dependencies:** Tasks 6, 7
**Estimated effort:** 20 min
**Commit scope:** `tests/test_file_graph.py` — add import matching and double-parse tests

**Description:**
Add tests for Phase 4 file_graph fixes:
- `test_import_matching_uses_ast_nodes()` — verify AST-based matching
- `test_import_matching_no_false_positives()` — no substring false matches
- `test_import_matching_from_import_statement()` — `from X import Y` handling
- `test_update_graph_no_double_parse()` — verify single parse via mock
- `test_update_graph_produces_same_edges()` — regression test

**Success criteria:**
- [ ] All 5 new tests pass
- [ ] Import matching tests use real Python files (not mocks)
- [ ] Double-parse test uses `unittest.mock.patch` to count parse calls
- [ ] `pytest tests/test_file_graph.py -v` passes
- [ ] Total test count increases to 115+

---

## Wave 4: Integration & Documentation (Tasks 12–13)
*Depends on all previous waves. Final wave.*

### Task 12: End-to-end integration test (all 5+ MCP tools)
**Type:** auto
**Dependencies:** Tasks 1–11
**Estimated effort:** 40 min
**Commit scope:** `tests/test_integration.py` — new file

**Description:**
Create integration tests exercising all MCP tools working together:
- Tools under test: `ping`, `store_messages`, `query_chat`, `list_sessions`, `get_context`, `track_files`, `get_file_graph`
- Test flow:
  1. `ping` → verify server responds
  2. `store_messages` → store test conversation
  3. `query_chat` → query stored messages
  4. `list_sessions` → verify session appears in index
  5. `get_context(detail_level="minimal")` → verify context compression
  6. `get_context(detail_level="summary")` → verify detail formatting
  7. `track_files` → build file graph for project
  8. `get_file_graph` → query file subgraph
  9. `prune_sessions` → verify cleanup works
- Each test uses isolated temp directory for ChromaDB and data files
- Verify JSON responses parse correctly
- Verify error handling (invalid params, missing data)

**Success criteria:**
- [ ] Integration test file exists at `tests/test_integration.py`
- [ ] All 7 MCP tools exercised in at least one test
- [ ] Tests use isolated temp directories (no cross-test pollution)
- [ ] Tests verify both success and error paths
- [ ] `pytest tests/test_integration.py -v` passes
- [ ] Total test count increases to 120+
- [ ] Test file has clear docstrings explaining each test scenario

---

### Task 13: Write comprehensive README.md
**Type:** auto
**Dependencies:** Tasks 1–12 (must reflect final state)
**Estimated effort:** 60 min
**Commit scope:** `README.md` — new file

**Description:**
Create comprehensive README per 4-CONTEXT.md Decision 6:
- **Architecture section:** High-level diagram (ASCII or mermaid) of system components
- **Installation:** Step-by-step setup with `uv` or `pip`
- **Quick Start:** Minimal example showing all tools
- **Tool Reference:** API documentation for each MCP tool:
  - `ping` — status check
  - `store_messages` — chat history storage
  - `query_chat` — semantic search with filters
  - `list_sessions` — session listing
  - `delete_session` — session deletion
  - `get_context` — token-efficient context retrieval (NEW)
  - `track_files` — file graph building
  - `get_file_graph` — file subgraph queries
  - `prune_sessions` — session cleanup (NEW)
- **Configuration:** `max_sessions`, chroma path, detail levels
- **FAQ:** Common questions and answers
- **Troubleshooting:** Model download issues, ChromaDB errors, import failures
- **Development:** How to run tests, contribute, project structure

**Success criteria:**
- [ ] `README.md` exists at project root
- [ ] Architecture diagram included (ASCII or mermaid)
- [ ] Installation instructions work on Windows + Linux
- [ ] All 9 MCP tools documented with parameters and examples
- [ ] At least one complete usage example per tool
- [ ] FAQ section with 3+ questions
- [ ] Troubleshooting section with 3+ common issues
- [ ] Development section explains how to run tests
- [ ] README renders correctly on GitHub (no broken formatting)

---

## Checkpoint: Final Verification
**Type:** checkpoint
**Dependencies:** Tasks 1–13
**Estimated effort:** 15 min

**Description:**
Run full verification suite and await user approval before marking Phase 4 (and entire project) complete.

**Verification steps:**
1. `pytest tests/ -v` — all tests pass (expect 120+)
2. `uv run python -m context_memory_mcp --help` — CLI works
3. `uv run python -m context_memory_mcp status` — shows version
4. Manual smoke test: start server, call `get_context`, verify output
5. Verify file tree matches expected structure
6. Review all 13 commit messages follow `[GSD-4-01-T{n}]` format
7. Verify no deviations from plan (or document in 4-01-SUMMARY.md)

**Acceptance criteria:**
- [ ] All 120+ tests pass
- [ ] CLI responds without errors
- [ ] `get_context` tool returns valid JSON with token count
- [ ] `prune_sessions` works correctly
- [ ] `list_sessions` uses session index (verified via profiling)
- [ ] Import matching uses AST parsing (verified via test)
- [ ] `update_graph` single-pass (verified via test)
- [ ] README.md comprehensive and renders correctly
- [ ] **STOP — wait for user approval** before marking Phase 4 complete

---

## Wave Structure Summary

| Wave | Tasks | Dependencies | Estimated Time |
|------|-------|-------------|----------------|
| **Wave 1** | T1, T2, T3, T4 | None | ~110 min |
| **Wave 2** | T5, T6, T7 | T4 (for T5) | ~85 min |
| **Wave 3** | T8, T9, T10, T11 | T4, T5, T6, T7 | ~95 min |
| **Wave 4** | T12, T13, Checkpoint | All previous waves | ~115 min |
| **Total** | **13 tasks + 1 checkpoint** | — | **~405 min (~6.75 hours)** |

## Dependency Graph

```
Wave 1:  T1 ──→ T2 ──→ T3
         T4 (independent)

Wave 2:  T5 (depends on T4)
         T6 (independent)
         T7 (independent)

Wave 3:  T8, T9 (independent)
         T10 (depends on T4, T5, T8, T9)
         T11 (depends on T6, T7)

Wave 4:  T12 (depends on T1–T11)
         T13 (depends on T1–T12)
         Checkpoint (depends on T1–T13)
```

## Implementation Notes (referencing 4-CONTEXT.md)

- **Token estimation** uses 4 chars/token heuristic (Decision 2) — accepted as approximate, not exact
- **Detail levels** follow numeric bounds: minimal ~100, summary ~300, full = raw (Decision 2)
- **Session index** is a separate JSON file at `./data/session_index.json` — updated atomically (MAJOR #2)
- **Import matching** must parse AST nodes, not substring match — use `import X` → module `X` extraction (MAJOR #3)
- **Double-parsing fix** retains symbols from first pass for edge extraction — no functional change, just performance (MAJOR #4)
- **query_chat validation** enforces ISO 8601 dates, handles `conversation_id` alias, returns `[]` for empty results (Decision 4)
- **README** must be comprehensive — architecture, all tools, FAQ, troubleshooting (Decision 6)
- **Out of scope** strictly enforced: no multi-user, cloud embeddings, VS Code extension, web visualization, Leiden, LLM summarization
