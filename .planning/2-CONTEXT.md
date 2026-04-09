# Phase 2 Context — Chat Memory

## Phase Goal
Implement full chat history persistence with ChromaDB, local embeddings, and MCP tools for storing and querying conversation history. This completes MVP.

---

## Decisions

### Decision 1: ChromaDB API Style
- **Decision:** Use `chromadb.PersistentClient(path="./data/chromadb")` (Option A)
- **Rationale:** Simplest approach — persistence is automatic, no manual `.persist()` calls needed. Clean API with minimal boilerplate.
- **Alternatives considered:** `chromadb.Client()` with explicit persist calls
- **Trade-offs:** Less control over flush timing, but for single-user local storage this is negligible. Path is relative to CWD.

### Decision 2: Embedding Integration
- **Decision:** Use ChromaDB's built-in `SentenceTransformerEmbeddingFunction` (Option A)
- **Rationale:** ChromaDB handles embedding transparently on store/query — less code, fewer failure modes. The `EmbeddingModel` placeholder class is not needed for Phase 2.
- **Alternatives considered:** Custom `EmbeddingModel` wrapper with pre-computed embeddings
- **Trade-offs:** Less granular control over embedding process, but ChromaDB's built-in function is well-tested and supports the same `sentence-transformers` models. If cross-module embedding reuse is needed later, we can extract it then.

### Decision 3: Tool Parameter Schema
- **Decision:** 
  - **`store_chat`**: Batch-first — `messages: list[{role, content}]`, `session_id: str | None = None`. Auto-generate session UUID if not provided.
  - **`query_chat`**: Full filtering — `query: str`, `top_k: int = 5`, `session_id: str | None`, `date_from: str | None`, `date_to: str | None`, `role: str | None`
- **Rationale:** User wants very large context memory for big projects. Batch ingestion is far more efficient for bulk message storage. Full filtering is essential when searching across large conversation histories.
- **Alternatives considered:** Flat single-message store, minimal query params
- **Trade-offs:** Slightly more complex tool schema, but much more practical at scale.

### Decision 4: Storage Path Configuration
- **Decision:** `./data/chromadb` relative to CWD (Option A)
- **Rationale:** Simple, visible, easy to inspect/debug. User can see the database files directly. For a personal weekend project, this is sufficient.
- **Alternatives considered:** Home directory path, environment variable configuration
- **Trade-offs:** Database path depends on CWD — if server is started from different directories, it creates separate databases. Can be made configurable later if needed.

### Decision 5: Session ID Handling
- **Decision:** `session_id` is optional — auto-generate UUID if not provided (Option B)
- **Rationale:** For very large context memory across big projects, automatic UUID generation removes friction while keeping conversations cleanly separated. Users can still provide explicit session IDs when they want to organize by project/feature.
- **Alternatives considered:** Required session_id, default to "default"
- **Trade-offs:** UUIDs are opaque — users need to track them externally if they want to reference specific sessions. The `list_sessions` tool (if added later) would help.

### Decision 6: Error Handling Strategy
- **Decision:** Let ChromaDB errors bubble up as-is (Option A)
- **Rationale:** Phase 2 is MVP scope — keep it simple. Raw errors are more informative for debugging. Can add wrapping in Phase 4 if UX demands it.
- **Alternatives considered:** Wrapped friendly errors, selective critical-only wrapping
- **Trade-offs:** User sees technical error messages, but this is a personal tool where debugging is acceptable.

### Decision 7: Testing Approach
- **Decision:** Include tests as part of Phase 2 tasks (Option A) — 9 tasks total
- **Rationale:** Catch issues early. The e2e persistence test (task 2.9) is critical for validating that Phase 2 actually works. Unit tests provide confidence before Phase 3/4 integration.
- **Alternatives considered:** Defer to Phase 4, minimal smoke test only
- **Trade-offs:** Adds ~1 task to Phase 2 workload, but prevents debugging pain later.

---

## Architecture

### Data Flow
```
MCP Client ──→ store_chat(messages, session_id?) ──→ ChatStore
                                                    │
                                                    ├── SentenceTransformerEmbeddingFunction (auto-embeds)
                                                    │
                                                    └── ChromaDB PersistentClient (./data/chromadb)
                                                              │
                                                              └── Collection: "chat_history"

MCP Client ──→ query_chat(query, top_k, filters) ──→ ChatStore
                                                     │
                                                     ├── ChromaDB query (semantic + where filters)
                                                     │
                                                     └── Return: [{content, role, timestamp, score}]
```

### ChromaDB Collection Schema
- **Collection name:** `chat_history`
- **Documents:** message content (text)
- **Metadatas:** `{session_id, role, timestamp}`
- **IDs:** auto-generated UUID per document
- **Embeddings:** auto-generated by `SentenceTransformerEmbeddingFunction`

### Embedding Model
- **Model:** `all-MiniLM-L6-v2` (default, lightweight, ~80MB download)
- **Dimension:** 384
- **Provider:** `chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction`

### Module Responsibilities
| Module | Responsibility |
|--------|---------------|
| `chat_store.py` | `ChatStore` class — store, query, list sessions, delete sessions |
| `embeddings.py` | Remains as placeholder — ChromaDB handles embeddings internally |
| `mcp_server.py` | Register `store_chat` and `query_chat` tools via `register(mcp)` in `chat_store.py` |

### Tool Signatures
```python
# store_chat — batch ingestion
async def store_chat(
    messages: list[dict[str, str]],  # [{"role": "user", "content": "..."}, ...]
    session_id: str | None = None,   # auto-generate UUID if not provided
) -> str:
    """Store chat messages with metadata. Returns JSON with stored count and session_id."""

# query_chat — semantic search with filters
async def query_chat(
    query: str,
    top_k: int = 5,
    session_id: str | None = None,
    date_from: str | None = None,   # ISO 8601: "2024-01-01T00:00:00"
    date_to: str | None = None,     # ISO 8601: "2024-01-31T23:59:59"
    role: str | None = None,        # "user" | "assistant" | "system"
) -> str:
    """Query chat history by semantic similarity. Returns JSON with results."""
```

---

## File Changes Expected
| File | Change |
|------|--------|
| `src/context_memory_mcp/chat_store.py` | **Replace** placeholder with full implementation |
| `src/context_memory_mcp/mcp_server.py` | **Update** `register_all()` to import chat_store register function |
| `pyproject.toml` | No changes (dependencies already present) |
| `tests/test_chat_store.py` | **Create** — unit + integration tests |

---

## Risks (Phase 2 Specific)
| # | Risk | Mitigation |
|---|------|------------|
| R2.1 | `sentence-transformers` model download is slow on first run | Model (`all-MiniLM-L6-v2`) is small (~80MB). Will download on first use. |
| R2.2 | ChromaDB `PersistentClient` path doesn't exist | Auto-create `./data/chromadb` directory on init. |
| R2.3 | Date filtering in ChromaDB uses string comparison | ChromaDB supports `where` clauses with `>=`/`<=` on string metadata if ISO 8601 format is used. |
| R2.4 | Large batch ingestion may hit ChromaDB limits | ChromaDB handles 10k+ documents per batch fine. If needed, chunk into sub-batches. |

---

## Out of Scope (Phase 2)
- `list_sessions` MCP tool (deferred — can be added in Phase 4)
- `delete_session` MCP tool (deferred)
- Message update/delete operations (store-only for now)
- Conversation summarization
- Cross-session semantic search optimization
