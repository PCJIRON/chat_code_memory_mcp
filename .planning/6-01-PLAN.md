# Phase 6: Hybrid Context System & Auto-Retrieve Fix — Plan 01

## Wave 1: Fix Auto-Retrieve Root Cause

### T1: Fix query extraction in mcp_server.py
**Problem:** `_intercepted_call_tool` passes tool name as query instead of actual user message.
**Solution:** Extract the actual user query from tool call arguments. For tools with `query` parameter, use that. For others, use the conversation context.
**File:** `src/context_memory_mcp/mcp_server.py`
**Commit:** `[GSD-6-01-T1] fix query extraction in auto-retrieve interceptor`

### T2: Verify monkey-patch actually triggers
**Problem:** Auto-save/auto-retrieve may not be firing at all.
**Solution:** Add debug logging, verify `_intercepted_call_tool` is actually called when tools execute. Check config flags.
**File:** `src/context_memory_mcp/mcp_server.py`, `src/context_memory_mcp/auto_retrieve.py`
**Commit:** `[GSD-6-01-T2] verify and fix monkey-patch interception mechanism`

---

## Wave 2: Hybrid Context Builder

### T3: Implement query classifier
**Description:** Rule-based intent classifier that routes queries to ChromaDB, FileGraph, or both.
**Logic:**
- Chat keywords: "discussed", "said", "remember", "previously", "what did we", "chat", "conversation"
- File keywords: "file", "changed", "import", "dependency", "class", "which files", "structure", "impact"
- If both present → BOTH
- If neither → BOTH (safe default)
**File:** `src/context_memory_mcp/context.py`
**Commit:** `[GSD-6-01-T3] implement query classifier for intent routing`

### T4: Implement HybridContextBuilder
**Description:** New context builder that:
1. Classifies query intent
2. Queries ChromaDB if chat intent
3. Queries FileGraph if file intent
4. Merges results, deduplicates
5. Fits within token budget
**File:** `src/context_memory_mcp/context.py`
**Commit:** `[GSD-6-01-T4] implement HybridContextBuilder with dual-source retrieval`

### T5: Rewrite get_context MCP tool
**Description:** Replace stub `get_context` with actual hybrid retrieval. Use `HybridContextBuilder` + `format_with_detail`.
**File:** `src/context_memory_mcp/context.py`
**Commit:** `[GSD-6-01-T5] rewrite get_context MCP tool with actual hybrid retrieval`

### T6: Add merge & dedup logic
**Description:** When both ChromaDB and FileGraph return results:
- Remove duplicate content
- Prioritize recent items
- Score by relevance
**File:** `src/context_memory_mcp/context.py`
**Commit:** `[GSD-6-01-T6] add merge and dedup logic for hybrid results`

### T7: Add token optimization
**Description:** Smart truncation within token budget:
- Prioritize user messages over assistant
- Prioritize recent over old
- Truncate long content with "..."
**File:** `src/context_memory_mcp/context.py`
**Commit:** `[GSD-6-01-T7] add token optimization to hybrid context builder`

---

## Wave 3: File Change History

### T8: Implement FileChangeLog class
**Description:** Append-only file change history tracker:
- `log_change(file_path, change_type, symbols_added, symbols_removed)`
- `query_changes(file_path=None, date_from=None, date_to=None, change_type=None)`
- `get_recent_changes(n=10)`
**Storage:** `./data/file_changes.json` (append-only with rotation)
**File:** `src/context_memory_mcp/file_history.py`
**Commit:** `[GSD-6-01-T8] implement FileChangeLog for time-based file history`

### T9: Hook FileChangeLog into track_files
**Description:** When `track_files` runs, compare with previous state and log deltas to FileChangeLog.
**File:** `src/context_memory_mcp/file_graph.py`, `src/context_memory_mcp/mcp_server.py`
**Commit:** `[GSD-6-01-T9] hook FileChangeLog into track_files MCP tool`

### T10: Add get_file_history MCP tool
**Description:** New tool to query file change history by date range, file path, or change type.
**File:** `src/context_memory_mcp/file_history.py`, `src/context_memory_mcp/mcp_server.py`
**Commit:** `[GSD-6-01-T10] register get_file_history MCP tool`

---

## Wave 4: Hybrid Auto-Retrieve

### T11: Update ContextInjector to use hybrid system
**Description:** Replace ChromaDB-only retrieval with `HybridContextBuilder`. Auto-retrieve now pulls from both sources.
**File:** `src/context_memory_mcp/auto_retrieve.py`
**Commit:** `[GSD-6-01-T11] update ContextInjector to use hybrid retrieval`

### T12: Improve auto-context injection format
**Description:** Better formatting so LLM actually uses the injected context:
- Clear header: `[Auto-Context: Recent conversation + file changes]`
- Structured format with sections
- Explicit instruction hint
**File:** `src/context_memory_mcp/auto_retrieve.py`
**Commit:** `[GSD-6-01-T12] improve auto-context format for LLM comprehension`

---

## Wave 5: Testing & Verification

### T13: Write tests for query classifier
**Description:** Test all intent classifications:
- Chat-only queries → CHAT
- File-only queries → FILE
- Mixed queries → BOTH
- Edge cases (empty, unknown keywords) → BOTH
**File:** `tests/test_context.py`
**Commit:** `[GSD-6-01-T13] add unit tests for query classifier`

### T14: Write tests for HybridContextBuilder
**Description:** Test hybrid retrieval with:
- Chat-only results
- File-only results
- Combined results with dedup
- Token budget enforcement
**File:** `tests/test_context.py`
**Commit:** `[GSD-6-01-T14] add unit tests for HybridContextBuilder`

### T15: Write tests for FileChangeLog + end-to-end
**Description:** 
- FileChangeLog: log, query, rotation
- End-to-end: store chat → change file → auto-retrieve → verify hybrid context
- Verify auto-retrieve works without manual prompting
**Files:** `tests/test_file_history.py`, `tests/test_auto_retrieve.py`
**Commit:** `[GSD-6-01-T15] add tests for FileChangeLog and e2e auto-retrieve`

### T16: Update README
**Description:** Document:
- Hybrid context system architecture
- Query classification behavior
- File change history usage
- Auto-retrieve fixed behavior
**File:** `README.md`
**Commit:** `[GSD-6-01-T16] update README with hybrid context documentation`

---

## Summary

- **Tasks:** 16
- **Waves:** 5
- **New Files:** `file_history.py`, `tests/test_file_history.py`
- **Modified Files:** `context.py`, `auto_retrieve.py`, `mcp_server.py`, `file_graph.py`, `README.md`, `tests/test_context.py`, `tests/test_auto_retrieve.py`
- **Expected Test Count:** 280+ (224 existing + ~56 new)
- **No New Dependencies**
