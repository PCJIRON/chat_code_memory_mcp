# Phase 6: Hybrid Context System & Auto-Retrieve Fix

## Problem Statement

### Issue 1: Auto-Retrieve Not Working
User has to manually tell LLM "every chat retrieve and store conversation" after each MCP connection. Auto-retrieve should work without any manual prompting.

**Root Causes Found:**
1. **Query Mismatch (CRITICAL):** `_intercepted_call_tool` passes tool *name* as query (e.g., `"query_chat"`) instead of actual user query (e.g., "how does vector search work"). ChromaDB searches for meaningless tool names.
2. **Single-Source Retrieval:** `ContextInjector` only queries ChromaDB — zero FileGraph integration.
3. **Conceptual Design Limitation:** Auto-context appended to tool response, not in system prompt. LLM doesn't know to use it unless explicitly told.

### Issue 2: `get_context` Is a Stub
`ContextBuilder.build()` returns only metadata (query echo, session ID, file count). **Zero retrieval** from either ChromaDB or FileGraph.

### Issue 3: No Hybrid System
ChromaDB and FileGraph work in isolation. No intelligent routing based on user intent. No unified context window combining both sources.

### Issue 4: No File Change History
FileGraph only tracks current state. No way to query "which files changed last week" or "what imports were added yesterday".

---

## Solution Architecture

### Hybrid Context System
```
User Query
    │
    ▼
┌──────────────────────┐
│ Query Classifier     │ ← Rule-based intent detection
│ (keyword matching)   │
└──────────┬───────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌───────────┐
│ChromaDB │ │ FileGraph │
│ (chat)  │ │ + History │
└────┬────┘ └─────┬─────┘
     │            │
     └─────┬──────┘
           ▼
┌──────────────────────┐
│ Merge & Deduplicate  │
│ Token Optimizer      │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Context Window       │
│ (token-budgeted)     │
└──────────────────────┘
```

### Query Classification
Rule-based keyword matching (no ML needed):
- **Chat intent:** "discussed", "said", "remember", "previously", "what did we", "chat", "conversation"
- **File intent:** "file", "changed", "import", "dependency", "class", "which files", "structure", "impact"
- **Both intent:** Keywords from both categories present
- **Unknown intent:** Default to BOTH (safe fallback)

### File Change History
Append-only `FileChangeLog` tracking:
- Timestamped file changes (modified/created/deleted)
- Symbol additions/removals per change
- Edge count deltas
- Queryable by date range, file path, or change type
- Stored as `./data/file_changes.json` with rotation

### Auto-Retrieve Fix
1. Extract actual user query from tool arguments (not tool name)
2. Use hybrid retrieval (ChromaDB + FileGraph + FileHistory)
3. Inject context with clear `[Auto-Context]` marker
4. Ensure interception actually triggers (verify monkey-patch)

---

## Success Criteria

- [ ] Auto-retrieve works without manual prompting
- [ ] `get_context` returns actual data from both ChromaDB and FileGraph
- [ ] Query classifier correctly routes intent 90%+ of the time
- [ ] File change history queryable by date range
- [ ] All 224 existing tests still pass
- [ ] New tests for hybrid system (target: 280+ total)
- [ ] README updated with hybrid behavior documentation

---

## Key Files to Modify/Create

| File | Action | Description |
|------|--------|-------------|
| `context.py` | **REWRITE** | Replace `ContextBuilder` with `HybridContextBuilder` |
| `auto_retrieve.py` | **MODIFY** | Update `ContextInjector` to use hybrid system + fix query extraction |
| `mcp_server.py` | **MODIFY** | Fix query extraction in `_wire_interception` |
| `file_graph.py` | **MODIFY** | Add `FileChangeLog` integration hooks |
| `file_history.py` | **CREATE** | New `FileChangeLog` class for time-based tracking |
| `test_context.py` | **MODIFY** | Add hybrid context tests |
| `test_auto_retrieve.py` | **MODIFY** | Fix tests for hybrid injector |
| `test_file_history.py` | **CREATE** | File change history tests |

---

## Estimated Complexity

| Wave | Tasks | Effort | Risk |
|------|-------|--------|------|
| 1: Fix Auto-Retrieve | 2 | 1 hour | Low |
| 2: Hybrid Context Builder | 5 | 4-5 hours | Medium |
| 3: File Change History | 3 | 2-3 hours | Low |
| 4: Hybrid Auto-Retrieve | 2 | 1-2 hours | Medium |
| 5: Testing & Verification | 3 | 2-3 hours | Low |
| **Total** | **15** | **10-14 hours** | **Medium** |

No new dependencies needed. All existing packages (ChromaDB, NetworkX, tree-sitter, watchdog).
