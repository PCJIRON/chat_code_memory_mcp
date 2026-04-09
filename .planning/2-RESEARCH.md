# Phase 2 Research — Chat Memory

## Phase Goals
Implement full chat history persistence with ChromaDB, local embeddings, and MCP tools for storing and querying conversation history. This completes MVP.

**Success Criteria:** Messages stored via MCP tool survive server restart, retrieved by semantic similarity with correct role/timestamp metadata.

---

## Approaches Considered

### Approach 1: ChromaDB PersistentClient + Built-in Embeddings (Selected)
**Description:** Use `chromadb.PersistentClient(path="./data/chromadb")` with `SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")` attached to the collection. ChromaDB handles embedding on every add/query transparently.

**Pros:**
- Minimal code — no manual embedding calls
- Proven, well-tested integration
- Model downloads automatically on first use (~80MB for MiniLM)
- Embeddings are always consistent (same function for add and query)

**Cons:**
- Model download blocks first `SentenceTransformerEmbeddingFunction` instantiation (~25s on first run)
- Can't pre-warm embeddings separately from storage

**Complexity:** Low
**Time Estimate:** 2-3 hours implementation

### Approach 2: Manual Embedding Pre-computation
**Description:** Use `sentence-transformers` directly to compute embeddings, then pass them to ChromaDB's `add()` as the `embeddings` parameter (bypassing collection-level embedding function).

**Pros:**
- Full control over embedding pipeline
- Can pre-compute and cache embeddings separately
- Can swap models without re-embedding

**Cons:**
- Double the code — manual embedding + ChromaDB storage
- Risk of embedding mismatch between add and query
- More failure modes

**Complexity:** Medium
**Time Estimate:** 3-4 hours

### Approach 3: SQLite + Full-Text Search (Alternative Storage)
**Description:** Use SQLite with FTS5 for text search instead of ChromaDB. Store embeddings as JSON blobs or skip vectors entirely.

**Pros:**
- No heavy dependencies (ChromaDB + sentence-transformers)
- SQLite is battle-tested on Windows
- FTS5 is fast for keyword search

**Cons:**
- No semantic similarity — only keyword/lexical search
- Loses the core value proposition (semantic search)
- Would need a separate vector solution anyway

**Complexity:** Medium
**Time Estimate:** 3-4 hours (but inferior results)

---

## Recommended Approach

**Selected:** Approach 1 — ChromaDB PersistentClient + Built-in Embeddings

**Why:** The 2-CONTEXT.md already decided this. My empirical testing confirms it works correctly with ChromaDB 1.5.7. The built-in embedding integration is clean and reliable. The only caveat is the first-run model download delay.

---

## Research Findings

### 1. ChromaDB PersistentClient API (v1.5.7)

**Version installed:** `1.5.7` (significantly newer than the `>=0.4.0` minimum in pyproject.toml)

**Initialization:**
```python
import chromadb

client = chromadb.PersistentClient(path="./data/chromadb")
# Auto-creates directory if it doesn't exist
# No manual .persist() calls needed — persistence is automatic
```

**Key client methods:**
- `client.get_or_create_collection(name, embedding_function, metadata)` — create or get collection
- `client.get_collection(name, embedding_function)` — get existing collection
- `client.list_collections()` — returns `Sequence[Collection]`
- `client.delete_collection(name)` — delete a collection
- `client.close()` — **critical on Windows** — releases SQLite file locks

**Collection creation:**
```python
from chromadb.utils import embedding_functions

ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

collection = client.get_or_create_collection(
    name="chat_history",
    embedding_function=ef,
    metadata={"hnsw:space": "cosine"},  # cosine similarity
)
```

**⚠️ Windows file lock issue:** On Windows, SQLite holds an exclusive lock on `chroma.sqlite3`. You **must** call `client.close()` before the process exits, otherwise:
- Temp directory cleanup fails with `PermissionError: [WinError 32]`
- Subsequent client instances to the same path may have issues

**Production pattern:**
```python
class ChatStore:
    def __init__(self, path: str = "./data/chromadb"):
        self._client = chromadb.PersistentClient(path=path)
        self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self._collection = self._client.get_or_create_collection(
            name="chat_history",
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    def close(self):
        self._client.close()
```

---

### 2. SentenceTransformerEmbeddingFunction

**Import and instantiation:**
```python
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
```

**Model details (`all-MiniLM-L6-v2`):**
- Size: ~80MB download (takes ~25s on first run)
- Dimensions: 384
- Cached in: `%USERPROFILE%\.cache\huggingface\hub\` on Windows
- First run triggers download from HuggingFace Hub
- Subsequent runs load from cache instantly

**How ChromaDB uses it:**
- On `collection.add(documents=[...])` → ChromaDB calls `ef(documents)` to generate embeddings automatically
- On `collection.query(query_texts=[...])` → ChromaDB calls `ef(query_texts)` to embed the query, then does vector search
- You **never** call the embedding function directly — ChromaDB handles it

**First-run behavior:**
```
Warning: You are sending unauthenticated requests to the HF Hub.
modules.json: 100%|██████████| 349/349
config.json: 100%|██████████| 612/612
model.safetensors: 100%|██████████| 90.9M/90.9M [00:24<00:00]
Loading weights: 100%|██████████| 103/103
tokenizer_config.json: 100%|██████████| 350/350
vocab.txt: 232kB
```

The HF Hub warning is harmless. The `LOAD REPORT` about `embeddings.position_ids` being UNEXPECTED is also harmless — it's a known artifact of loading from a different checkpoint format.

**⚠️ No `sentence-transformers` import needed:** Despite having `sentence-transformers>=2.2.0` in pyproject.toml, you don't import it directly. ChromaDB's `SentenceTransformerEmbeddingFunction` handles the import internally.

---

### 3. ChromaDB Metadata Filtering (v1.5.7)

**CRITICAL FINDING:** ChromaDB 1.5.7 has **major changes** to metadata filtering compared to older documentation.

#### What Works

**Equality (implicit, no operator needed):**
```python
# Simple equality
collection.query(query_texts=["hello"], n_results=5, where={"role": "user"})

# Explicit equality
collection.query(query_texts=["hello"], n_results=5, where={"role": {"$eq": "user"}})
```

**`$in` and `$nin` for multiple values:**
```python
# Match any of these session IDs
collection.query(query_texts=["hello"], n_results=10,
    where={"session_id": {"$in": ["sess-a", "sess-b"]}})
```

**`$and` and `$or` for combining conditions:**
```python
# Both conditions must match
collection.query(query_texts=["hello"], n_results=10,
    where={"$and": [
        {"session_id": "sess-a"},
        {"role": "user"},
    ]})
```

**`$ne` (not equal):**
```python
collection.query(query_texts=["hello"], n_results=10, where={"role": {"$ne": "system"}})
```

**`$contains` and `$not_contains` on metadata:**
- **Does NOT work on string metadata values** — returns 0 results
- Designed for list/array-type metadata, not string substring matching
- **Do not use for string filtering**

**`where_document` for text content filtering:**
```python
# Document contains substring
collection.query(query_texts=["hello"], n_results=10,
    where_document={"$contains": "error"})

# Document does NOT contain
collection.query(query_texts=["hello"], n_results=10,
    where_document={"$not_contains": "debug"})

# Document regex match
collection.query(query_texts=["hello"], n_results=10,
    where_document={"$regex": "error|exception"})
```

#### What DOES NOT Work (Critical)

**`$gte`/`$lte`/`$gt`/`$lt` on string metadata:**
```python
# THIS FAILS with:
# ValueError: Expected operand value to be an int or a float for operator $gte
collection.query(query_texts=["hello"], n_results=10,
    where={"timestamp": {"$gte": "2024-01-15T00:00:00"}})
# ❌ FAILS — $gte/$lte only work on numeric metadata values!

# Even combining with $and fails:
collection.query(query_texts=["hello"], n_results=10,
    where={"$and": [
        {"timestamp": {"$gte": "2024-01-15T00:00:00"}},
        {"timestamp": {"$lte": "2024-01-15T23:59:59"}},
    ]})
# ❌ FAILS — same error
```

**`$gte`/`$lte` on integers DOES work:**
```python
# This works fine — token_count is an integer
collection.query(query_texts=["hello"], n_results=10,
    where={"token_count": {"$gte": 200}})
# ✅ Works
```

#### Date Filtering — Python Post-Processing Required

Since ChromaDB doesn't support range operators on string metadata, date filtering **must** be done in Python after retrieving results:

```python
def query_chat(self, query: str, top_k: int = 5,
               session_id: str | None = None,
               date_from: str | None = None,
               date_to: str | None = None,
               role: str | None = None) -> list[dict]:
    # Build ChromaDB where clause (only equality/in/and/or)
    where = self._build_where(session_id, role)

    # Query ChromaDB with a large n_results to get enough candidates
    result = self._collection.query(
        query_texts=[query],
        n_results=max(top_k * 3, 50),  # over-fetch for post-filtering
        where=where if where else None,
        include=["documents", "metadatas", "distances"],
    )

    # Apply date filtering in Python
    filtered_docs = []
    for i in range(len(result["documents"][0])):
        ts = result["metadatas"][0][i]["timestamp"]
        if date_from and ts < date_from:
            continue
        if date_to and ts > date_to:
            continue
        filtered_docs.append({
            "content": result["documents"][0][i],
            "role": result["metadatas"][0][i]["role"],
            "timestamp": ts,
            "distance": result["distances"][0][i],
        })

    return filtered_docs[:top_k]
```

**Why `n_results=top_k * 3`:** Since date filtering happens after ChromaDB returns results, we need to over-fetch to ensure we have enough candidates after date filtering. The multiplier of 3 is a practical heuristic — if top_k=5, we fetch 15 results and then filter down.

#### Available `include` Values

| Include | Description | Always returned? |
|---------|-------------|-----------------|
| `documents` | The text content | No |
| `metadatas` | Metadata dicts | No |
| `distances` | Cosine distances | No |
| `ids` | Document IDs | **YES** — always present regardless of include |
| `embeddings` | Vector embeddings | No |
| `uris` | URIs (if using image/uri storage) | No |
| `data` | Raw data blobs | No |

**Note:** In ChromaDB 1.5.7, the result dict always contains all keys (`ids`, `embeddings`, `documents`, `uris`, `included`, `data`, `metadatas`, `distances`) regardless of the `include` parameter. Values for non-included items may be `None` or empty lists. This is different from older versions.

**`get()` vs `query()`:**
- `collection.get(where=..., include=[...])` — retrieves documents by filter, no semantic search
- `collection.get()` **does NOT support** `distances` in include (raises `ValueError`)
- `collection.query()` — semantic search with optional filter

#### Query Result Structure

```python
result = collection.query(
    query_texts=["how does chromadb work"],
    n_results=3,
    where={"session_id": "sess-001"},
    include=["documents", "metadatas", "distances"],
)

# Result is a dict with these keys:
{
    "ids": [["id-1", "id-2", "id-3"]],           # List[List[str]] — always present
    "documents": [["doc text 1", "doc text 2"]],  # List[List[str]]
    "metadatas": [[{"role": "user", ...}, ...]],  # List[List[dict]]
    "distances": [[0.4187, 0.7973]],              # List[List[float]]
}
```

**Key observation:** All values are **double-nested** — `result["documents"]` is `List[List[str]]`, not `List[str]`. The outer list is because `query_texts` accepts multiple queries. For a single query, always access index `[0]`.

---

### 4. FastMCP Tool Registration Pattern

**Import:**
```python
from mcp.server.fastmcp import FastMCP
```

**Tool decorator signature:**
```python
@mcp.tool(
    name="store_chat",        # Optional — defaults to function name
    description="Store chat messages",  # Required for MCP tool description
)
async def store_chat(...) -> str:
    ...
```

**Tool params with descriptions using `Annotated` + `Field`:**
```python
from typing import Annotated
from pydantic import Field

@mcp.tool(name="store_chat", description="Store chat messages in history")
async def store_chat(
    messages: Annotated[
        list[dict[str, str]],
        Field(description='List of message objects with "role" and "content" keys')
    ],
    session_id: Annotated[
        str | None,
        Field(description="Session UUID. Auto-generated if not provided")
    ] = None,
) -> str:
    """Store a batch of chat messages with optional session ID."""
    ...
```

**✅ Verified working:** Both `list[dict[str, str]]` and `str | None` types work correctly with FastMCP's decorator. The `Annotated[Type, Field(...)]` pattern is the correct way to add parameter descriptions.

**Full tool example with all parameter types:**
```python
from mcp.server.fastmcp import FastMCP
from typing import Annotated
from pydantic import Field
import json

mcp = FastMCP("context-memory-mcp")

@mcp.tool(
    name="store_chat",
    description="Store chat messages in conversation history",
)
async def store_chat(
    messages: Annotated[
        list[dict[str, str]],
        Field(description='List of {role: "user"|"assistant"|"system", content: str} objects')
    ],
    session_id: Annotated[
        str | None,
        Field(description="Session UUID. Auto-generated if omitted")
    ] = None,
) -> str:
    count = len(messages)
    return json.dumps({"stored": count, "session_id": session_id or "<auto-generated>"})


@mcp.tool(
    name="query_chat",
    description="Search chat history by semantic similarity",
)
async def query_chat(
    query: Annotated[
        str,
        Field(description="Natural language search query")
    ],
    top_k: Annotated[
        int,
        Field(description="Number of results to return", ge=1, le=50)
    ] = 5,
    session_id: Annotated[
        str | None,
        Field(description="Filter to specific session")
    ] = None,
    date_from: Annotated[
        str | None,
        Field(description="ISO 8601 start date (e.g. 2024-01-01T00:00:00)")
    ] = None,
    date_to: Annotated[
        str | None,
        Field(description="ISO 8601 end date")
    ] = None,
    role: Annotated[
        str | None,
        Field(description='Filter by role: "user", "assistant", "system"')
    ] = None,
) -> str:
    """Query chat history with semantic search and optional filters."""
    ...
```

**Module registration pattern (Option B — already in use):**
```python
# chat_store.py
def register(mcp: FastMCP) -> None:
    """Register chat memory tools."""
    @mcp.tool(name="store_chat", description="...")
    async def store_chat(...): ...

    @mcp.tool(name="query_chat", description="...")
    async def query_chat(...): ...

# mcp_server.py — update register_all()
def register_all() -> None:
    _register_core(mcp)
    from context_memory_mcp.chat_store import register as register_chat
    register_chat(mcp)
```

---

### 5. ChromaDB Query Result Format → MCP Output

**Raw query result:**
```python
result = collection.query(
    query_texts=["how does it work"],
    n_results=3,
    include=["documents", "metadatas", "distances"],
)

# Returns:
{
    "ids": [["id-4", "id-1", "id-2"]],
    "documents": [["Can you explain...", "The project uses...", "I need help..."]],
    "metadatas": [
        [
            {"session_id": "sess-002", "role": "user", "timestamp": "2024-01-16T14:00:00"},
            {"session_id": "sess-001", "role": "user", "timestamp": "2024-01-15T10:00:00"},
            {"session_id": "sess-001", "role": "assistant", "timestamp": "2024-01-15T10:00:05"},
        ]
    ],
    "distances": [[0.4187, 0.7973, 0.8792]],
}
```

**MCP tool output format (JSON string):**
```python
def _format_query_results(self, result: dict, top_k: int) -> list[dict]:
    """Convert ChromaDB query result to MCP tool response format."""
    results = []
    for i in range(len(result["documents"][0])):
        results.append({
            "content": result["documents"][0][i],
            "role": result["metadatas"][0][i]["role"],
            "timestamp": result["metadatas"][0][i]["timestamp"],
            "session_id": result["metadatas"][0][i]["session_id"],
            "distance": round(result["distances"][0][i], 4),
            "similarity": round(1 - result["distances"][0][i], 4),  # cosine distance → similarity
        })
    return results[:top_k]

# MCP tool returns:
return json.dumps({
    "query": query,
    "results": formatted_results,
    "total_found": len(formatted_results),
}, indent=2)
```

---

### 6. Windows-Specific Risks

| Risk | Status | Mitigation |
|------|--------|------------|
| **SQLite file lock** | ✅ Confirmed | Call `client.close()` before process exit. The lock prevents temp directory cleanup and may block concurrent access. |
| **Path length (MAX_PATH=260)** | ⚠️ Potential | `./data/chromadb` is short enough. If users place the project in deeply nested paths, ChromaDB's internal structure (`chroma.sqlite3` + `chroma.parquet` files) could hit limits. Use short CWD paths. |
| **sentence-transformers model download** | ✅ Works | Model downloads correctly on Windows. ~25s download time for MiniLM. Cached after first run. The HF Hub warning is cosmetic. |
| **ChromaDB `PersistentClient` path creation** | ✅ Works | `PersistentClient` auto-creates the directory. No manual `os.makedirs()` needed. |
| **Concurrent access** | ⚠️ Untested | ChromaDB uses SQLite — only one writer at a time. For single-user MCP server, this is fine. |
| **HF token warning** | ✅ Cosmetic | `Warning: You are sending unauthenticated requests to the HF Hub` — harmless. Can set `HF_TOKEN` env var for faster downloads. |

---

### 7. Batch Ingestion Best Practices

**Document IDs:** Use UUIDs as document IDs. ChromaDB **rejects duplicate IDs** on `add()` with an error:
```python
# Using uuid4 for each message
import uuid

ids = [str(uuid.uuid4()) for _ in messages]
collection.add(ids=ids, documents=docs, metadatas=metas)
```

**Batch size limits:** ChromaDB 1.5.7 handles 10k+ documents per batch without issue. For chat messages, typical batches are 5-100 messages — well within limits.

**`add()` vs `upsert()`:**
- `add()` — **fails** if any ID already exists. Use when you're sure messages are new.
- `upsert()` — inserts new or updates existing. Use when you need idempotency.

**Recommended pattern for `store_chat`:**
```python
def store_messages(self, messages: list[dict], session_id: str | None = None) -> dict:
    """Batch store chat messages."""
    if session_id is None:
        session_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc).isoformat()
    ids = [str(uuid.uuid4()) for _ in messages]
    documents = [msg["content"] for msg in messages]
    metadatas = [
        {
            "session_id": session_id,
            "role": msg.get("role", "user"),
            "timestamp": msg.get("timestamp", now),
        }
        for msg in messages
    ]

    self._collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    return {"stored": len(messages), "session_id": session_id}
```

**Metadata constraints:**
- Metadata values must be `str`, `int`, `float`, or `bool`
- No nested dicts or lists in metadata
- Keep timestamps as ISO 8601 strings for Python-side date filtering

---

## Implementation Notes

### ChatStore Class Structure

The existing `chat_store.py` has a placeholder with `ChatMessage` and `ChatStore` classes. The placeholder methods (`add_message`, `get_session_messages`, `search_similar`, `delete_session`, `list_sessions`) have **different signatures** than what the MCP tools need.

**Recommendation:** Keep the class structure but implement methods that match the MCP tool needs:
- `store_messages(messages, session_id)` → batch store
- `query_messages(query, top_k, session_id, date_from, date_to, role)` → semantic search with filters
- `list_sessions()` → distinct session IDs (via `get()` + dedupe)
- `delete_session(session_id)` → delete by where clause

The `ChatMessage` dataclass can be kept as a convenience for internal use but isn't strictly needed — raw dicts work fine.

### Where Clause Builder Pattern

```python
def _build_where(self, session_id: str | None = None,
                 role: str | None = None) -> dict | None:
    conditions = []
    if session_id:
        conditions.append({"session_id": session_id})
    if role:
        conditions.append({"role": role})
    if len(conditions) == 0:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}
```

### Date Filtering Strategy

Since `$gte`/`$lte` don't work on strings:
1. Query ChromaDB with session_id and role filters only (equality works)
2. Use a generous `n_results` (e.g., `top_k * 3`) to over-fetch
3. Apply date range filtering in Python using string comparison (ISO 8601 strings compare correctly lexicographically)
4. Slice to `top_k`

### Existing `embeddings.py`

This file remains a placeholder. ChromaDB's `SentenceTransformerEmbeddingFunction` handles embeddings internally. The `EmbeddingModel` class can be removed or left as-is for potential future use (e.g., if custom embedding logic is needed in Phase 4).

---

## Libraries/Tools

| Library | Version | Why |
|---------|---------|-----|
| `chromadb` | 1.5.7 (installed) | Vector store with built-in embedding support |
| `chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction` | — | Attaches MiniLM model to collection; auto-embeds on add/query |
| `mcp.server.fastmcp.FastMCP` | from `mcp>=1.0.0` | MCP server framework with `@mcp.tool()` decorator |
| `pydantic.Field` | from pydantic (transitive dep of mcp) | Parameter descriptions in tool schemas |
| `typing.Annotated` | Python 3.11+ stdlib | Attach Field metadata to function params |
| `uuid.uuid4` | Python stdlib | Generate session IDs and document IDs |

---

## Pitfalls to Avoid

1. **❌ Don't use `$gte`/`$lte` on timestamp metadata** — ChromaDB 1.5.7 only supports range operators on numeric values. Use Python string comparison after fetching results.

2. **❌ Don't use `$contains` on string metadata** — It returns 0 results. It's designed for list/array types. Use `where_document={"$contains": "..."}` for text filtering or Python post-processing.

3. **❌ Don't forget `client.close()`** — On Windows, SQLite file locks prevent cleanup and may cause issues. Always close the client.

4. **❌ Don't access `result["documents"]` directly** — It's `List[List[str]]`. Use `result["documents"][0]` for single-query results.

5. **❌ Don't include `"ids"` in the `include` list** — `ids` is not a valid include value. It's always returned automatically.

6. **❌ Don't use `get()` with `distances`** — Raises `ValueError`. Only `query()` supports distances.

7. **❌ Don't rely on default `n_results=10`** — For filtered queries, the default 10 may not be enough after date filtering. Use a larger value and slice after Python filtering.

8. **⚠️ Don't store nested metadata values** — ChromaDB metadata only supports flat `str|int|float|bool`. No nested dicts or lists.

9. **⚠️ First-run model download** — The `all-MiniLM-L6-v2` model takes ~25s to download. This happens on first `SentenceTransformerEmbeddingFunction` instantiation. Users will see download progress on first server start.

10. **⚠️ Don't mix `PersistentClient` paths** — `./data/chromadb` is relative to CWD. If the server is started from different directories, it creates separate databases. Document this clearly.

---

## Codebase Patterns (Brownfield)

- **Follow existing module registration pattern:** Each domain module has a `register(mcp: FastMCP)` function. `mcp_server.py` calls them in `register_all()`.
- **Follow existing tool response format:** The ping tool returns `json.dumps({...})`. Chat tools should do the same.
- **Use `from __future__ import annotations`** — Consistent with all existing modules.
- **Follow existing import style:** `from mcp.server.fastmcp import FastMCP` (already used in `mcp_server.py`).
- **Update `mcp_server.py` `register_all()`:** Uncomment the Phase 2 import and call:
  ```python
  from context_memory_mcp.chat_store import register as register_chat
  register_chat(mcp)
  ```
- **Tests directory is empty** — Create `tests/test_chat_store.py` with pytest tests.
- **Existing `test_ping_stdio.py`** in `scripts/` shows the JSON-RPC protocol for testing tools over stdio.

---

## Summary: Key Implementation Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| ChromaDB client | `PersistentClient(path="./data/chromadb")` | Simplest, auto-persists |
| Embedding method | `SentenceTransformerEmbeddingFunction("all-MiniLM-L6-v2")` | Built-in, minimal code |
| Document IDs | `uuid.uuid4()` per message | Unique, no duplicates |
| Session ID | Auto-generate `uuid4()` if not provided | Frictionless UX |
| Date filtering | Python post-processing with string comparison | ChromaDB doesn't support range ops on strings |
| Metadata filtering | `$and` with equality conditions | Only working approach in v1.5.7 |
| Error handling | Bubble up raw ChromaDB errors | MVP scope, per 2-CONTEXT.md Decision 6 |
| Tool response format | `json.dumps({...})` string | Consistent with ping tool |
| Windows file locks | `client.close()` on cleanup | Prevents SQLite lock issues |
