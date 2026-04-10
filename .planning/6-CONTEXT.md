# Phase 6: Hybrid Context System & Auto-Retrieve Fix

## Implementation Decisions

### Decision 1: Context Injection Strategy
- **Decision:** Both system prompt + response append (dual injection)
- **Rationale:** System prompt ensures LLM sees context upfront; response append provides fallback
- **Alternatives considered:** Response-only (current, LLM ignores it), System-prompt-only (harder with FastMCP)
- **Trade-offs:** More complex implementation but maximum reliability

### Decision 2: Query Classification Approach
- **Decision:** Semantic classifier using existing `sentence-transformers` model (NOT keyword matching)
- **Rationale:** User wants semantic understanding — model should understand intent, not match words
- **Alternatives considered:** Rule-based keywords (rejected), ML with new model (rejected), Rules+LLM fallback (rejected — costs tokens)
- **Trade-offs:** Uses already-downloaded model (zero new deps), semantic understanding, ~90%+ accuracy. Slightly more latency than keywords but much smarter.
- **Implementation:** Embed user query → compare against pre-computed intent centroids (chat_intent vs file_intent vectors) → classify by nearest centroid

### Decision 3: File Change History Storage
- **Decision:** Store file changes in ChromaDB alongside chat messages (unified vector storage)
- **Rationale:** Single query searches both chat history AND file changes semantically — no separate storage needed
- **Alternatives considered:** JSON file (rejected), SQLite (rejected), Separate ChromaDB collection (rejected — defeats unified search purpose)
- **Trade-offs:** Simpler architecture (one DB), semantic search across chat+files. ChromaDB handles all filtering. No new persistence logic.
- **Implementation:** File changes stored as ChromaDB documents with metadata: `{type: "file_change", file_path, change_type, symbols_added, symbols_removed, snippet, timestamp}`

### Decision 4: File Change Tracking Granularity
- **Decision:** Full tracking — file path + timestamp + change type + symbol diff + code snippets
- **Rationale:** User wants complete context — what changed, when, and actual code
- **Alternatives considered:** Basic (path+time+type), Detailed (+symbols only)
- **Trade-offs:** Higher storage cost but enables richest queries ("what imports changed last week", "show me the function that was modified")

---

## Updated Architecture

### Unified ChromaDB Storage
```
ChromaDB Collection
├── Chat Messages (role, content, timestamp, session_id)
└── File Changes (type, file_path, change_type, symbols, snippet, timestamp)
```

### Semantic Query Flow
```
User Query
    │
    ▼
┌──────────────────────────┐
│ Semantic Classifier      │ ← sentence-transformers embedding
│ (intent centroids)       │ ← Zero new dependencies
└──────────┬───────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌─────────────────┐
│ChromaDB │ │ ChromaDB        │
│ (chat)  │ │ (file changes)  │
└────┬────┘ └─────┬──────────┘
     │            │
     └─────┬──────┘
           ▼
┌──────────────────────┐
│ Merge & Deduplicate  │
│ Token Optimizer      │
└──────────┬───────────┘
           ▼
┌──────────────────────────────┐
│ Dual Context Injection       │
│ 1. System prompt prepend     │
│ 2. Response append fallback  │
└──────────────────────────────┘
```

### Intent Centroids (Pre-computed)
```python
CHAT_INTENT_EMBEDDING = embed("what did we discuss previously remember conversation said")
FILE_INTENT_EMBEDDING = embed("which file changed import dependency structure impact")
# User query embedded → nearest centroid determines intent
```

---

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
