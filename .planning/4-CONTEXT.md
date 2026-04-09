# Phase 4 Context — Integration & Polish

## Phase Goal
Implement token-efficient context retrieval, detail-level formatting, enhance `query_chat` filtering, fix 4 deferred MAJOR items from Phases 2/3, add integration tests, and write comprehensive README. This is the **final phase** — project complete after this.

---

## Decisions

### Decision 1: Token Compression Strategy
- **Decision:** Hybrid approach — template-based formatting + smart truncation to fit ~100 token budget
- **Rationale:** Large projects generate massive context that needs aggressive compression. Small projects benefit from the same mechanism — it just won't compress as much. The hybrid approach works at any scale.
- **Alternatives considered:** Keyword extraction only, pure summarization, LLM-based summarization
- **Trade-offs:** Template approach preserves conversation structure better than keyword-only. Won't be as good as LLM summarization but zero API cost and fully local.

### Decision 2: Detail Level Output Format
- **Decision:** Token-budgeted levels — `minimal` (~100 tokens), `summary` (~300 tokens), `full` (raw messages)
- **Rationale:** Clear numeric bounds make it predictable for LLM consumption. `minimal` fits in tight context windows, `summary` provides useful overview, `full` is everything. Works for small and large projects equally.
- **Alternatives considered:** Fixed message counts (last 3/10/all), topic-keyword-only modes
- **Trade-offs:** Token estimation is heuristic-based (4 chars/token), not exact. But good enough for MVP.

### Decision 3: Deferred MAJOR Items — All Fixed in Phase 4
- **Decision:** Fix all 4 MAJOR items as part of Phase 4 execution
- **Rationale:** User wants to work on large projects. These items become blockers at scale:
  - **MAJOR #1 (Phase 2):** Session cleanup — `prune_sessions(before_date)` method + optional `max_sessions` config
  - **MAJOR #2 (Phase 2):** `list_sessions()` O(n) — use separate session index (JSON file or ChromaDB metadata)
  - **MAJOR #3 (Phase 3):** Fragile import matching — parse module names from AST nodes instead of substring matching
  - **MAJOR #4 (Phase 3):** Double-parsing in `update_graph` — retain symbols from first pass for edge extraction
- **Alternatives considered:** Defer to post-MVP, fix only Phase 2 items
- **Trade-offs:** Adds ~4 tasks to Phase 4 scope. But these are real scalability blockers for large projects.

### Decision 4: `query_chat` Enhancement
- **Decision:** Re-implement with proper validation and edge case handling
- **Rationale:** Phase 2 already has `date_from`/`date_to`/`session_id`/`role` parameters, but for large projects we need:
  - Input validation on date formats (ISO 8601 enforcement)
  - Proper handling of `conversation_id` as alias for `session_id`
  - Edge case: empty results return `[]` not error
  - Edge case: conflicting date ranges handled gracefully
- **Alternatives considered:** Skip (already done), defer validation to post-MVP
- **Trade-offs:** Adds validation overhead but prevents confusing errors at scale.

### Decision 5: Testing Strategy
- **Decision:** Focus new tests on Phase 4 features (context compression, detail levels, integration)
- **Rationale:** Existing 99 tests provide strong coverage for parser, file_graph, and chat_store basics. Phase 4 needs:
  - Unit tests for `get_minimal_context()` and `format_with_detail()`
  - Integration tests for all 5 MCP tools working together
  - Tests for the 4 MAJOR fixes
- **Alternatives considered:** Write all tests from scratch, add only integration tests
- **Trade-offs:** Reuses existing test infrastructure, avoids duplication.

### Decision 6: README Scope
- **Decision:** Comprehensive README — architecture diagram, all tools with examples, FAQ, troubleshooting
- **Rationale:** Large projects need proper documentation. Users need to understand:
  - How the system works (architecture)
  - What each tool does (API reference)
  - How to set it up (installation)
  - What to do when things break (troubleshooting)
- **Alternatives considered:** Minimal README (30 min), auto-generated API docs
- **Trade-offs:** ~2 hour effort but essential for project completeness.

---

## Architecture

### Context Compression Pipeline
```
query_chat results ──→ get_minimal_context() ──→ format_with_detail(level) ──→ JSON response
      │                        │                          │
      ├── Recent messages      ├── ~100 token budget      ├── minimal: key info only
      ├── Active file context  ├── Smart truncation       ├── summary: + headers + detail
      └── Semantic matches     └── Template formatting    └── full: raw results
```

### New Module: `src/context_memory_mcp/context.py`
| Class/Function | Responsibility |
|----------------|---------------|
| `ContextWindow` | Token-limited context container (already placeholder) |
| `ContextBuilder` | Assembles context from multiple sources |
| `get_minimal_context(messages)` | Compress to ~100 tokens |
| `format_with_detail(results, level)` | Format output by detail level |
| `register(mcp)` | Register `get_context` MCP tool |

### Session Index (MAJOR #2 Fix)
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
- Separate JSON file at `./data/session_index.json`
- Updated on every `store_messages()` call
- `list_sessions()` reads index instead of fetching entire collection

### Prune Strategy (MAJOR #1 Fix)
```python
def prune_sessions(self, before_date: str | None = None, max_sessions: int | None = None) -> dict:
    """Remove old sessions to control collection size."""
    # Option A: Delete all sessions before a date
    # Option B: Keep only the N most recent sessions
    # Returns: {"pruned": count, "remaining": count}
```

---

## Phase 4 Expanded Task List

### From Roadmap (9 tasks)
| Task | Description | Commit Title |
|------|-------------|-------------|
| 4.1 | `get_minimal_context()` — compress to ~100 tokens | `[GSD-4-01-T1] implement get_minimal_context compression` |
| 4.2 | `format_with_detail()` — minimal/summary/full modes | `[GSD-4-01-T2] implement detail_level formatting` |
| 4.3 | Register `get_context` MCP tool | `[GSD-4-01-T3] register get_context MCP tool` |
| 4.4 | `conversation_id` filter on `query_chat` | `[GSD-4-01-T4] add conversation_id filter to query_chat` |
| 4.5 | Date range filter on `query_chat` | `[GSD-4-01-T5] add date range filter to query_chat` |
| 4.6 | Unit tests for chat_store | `[GSD-4-01-T6] add unit tests for chat_store` |
| 4.7 | Unit tests for file_graph | `[GSD-4-01-T7] add unit tests for file_graph` |
| 4.8 | End-to-end integration test | `[GSD-4-01-T8] add end-to-end integration test` |
| 4.9 | Write README.md | `[GSD-4-01-T9] write README with setup and usage docs` |

### Deferred MAJOR Fixes (4 additional tasks)
| Task | Description | Commit Title |
|------|-------------|-------------|
| 4.10 | `prune_sessions()` method + max_sessions config | `[GSD-4-01-T10] add session pruning mechanism` |
| 4.11 | Session index JSON — eliminate O(n) `list_sessions()` | `[GSD-4-01-T11] optimize list_sessions with session index` |
| 4.12 | Fix import matching — parse AST nodes not substring match | `[GSD-4-01-T12] fix import matching with AST node parsing` |
| 4.13 | Fix double-parsing in `update_graph` | `[GSD-4-01-T13] eliminate double-parsing in update_graph` |

**Total:** 13 tasks

---

## File Changes Expected
| File | Change |
|------|--------|
| `src/context_memory_mcp/context.py` | **Replace** placeholder with full implementation |
| `src/context_memory_mcp/chat_store.py` | **Update** — add `prune_sessions()`, session index, validation |
| `src/context_memory_mcp/file_graph.py` | **Update** — fix import matching, fix double-parsing |
| `src/context_memory_mcp/mcp_server.py` | **Update** — register context tools |
| `tests/test_context.py` | **Create** — context compression tests |
| `tests/test_chat_store.py` | **Update** — add prune/index tests (if not present) |
| `tests/test_integration.py` | **Create** — end-to-end MCP tool tests |
| `README.md` | **Create** — comprehensive documentation |

---

## Risks (Phase 4 Specific)
| # | Risk | Mitigation |
|---|------|------------|
| R4.1 | `sentence-transformers` model download blocks offline first run | Model already downloaded during Phase 2. Should be cached. Verify before Phase 4. |
| R4.2 | Feature creep — adding Leiden, D3, multi-user | Enforce "Out of Scope" list strictly. This is the final phase. |
| R4.3 | Token estimation heuristic (4 chars/token) is inaccurate for code | Accept inaccuracy — it's an estimate, not a hard limit. Good enough for MVP. |
| R4.4 | Session index JSON gets out of sync with ChromaDB | Update index atomically on every store/delete operation. |

---

## Out of Scope (Phase 4 — Final Enforcement)
These remain **explicitly excluded**:
- Multi-user support / authentication
- Cloud embeddings (OpenAI, Google, etc.)
- VS Code extension
- Web visualization (D3.js)
- Community detection (Leiden algorithm)
- Execution flow analysis
- Risk scoring / refactoring tools
- Multi-repo registry
- `watchdog` file system watcher
- LLM-based summarization
