# Phase 6 Research

## Phase Goals

Fix broken auto-retrieve and build a hybrid ChromaDB + FileGraph context system with semantic query classification. Specifically:

1. **Fix auto-retrieve root cause** — `_intercepted_call_tool` passes tool NAME as query instead of actual user message
2. **Build hybrid context builder** — combine ChromaDB (semantic chat + file changes) with FileGraph (structural dependencies)
3. **Implement semantic intent classification** — use existing `sentence-transformers` model to classify user intent (chat vs file)
4. **Store file changes in ChromaDB** — unified vector storage for both chat and file change history
5. **Improve context injection** — dual injection (system prompt prepend + response append fallback)

## Approaches Considered

### Research Area 1: FastMCP System Prompt Injection

#### Approach 1A: Use `instructions` parameter at FastMCP construction
**Description:** FastMCP accepts `instructions: str | None` in `__init__`, which maps to `self._mcp_server.instructions`. This is the MCP protocol's native "system prompt" — sent to the LLM during the `initialize` handshake. Set it once at startup with static context about the MCP server's capabilities.

**Pros:** Native MCP protocol support, LLM sees it automatically on every connection, zero monkey-patching needed.
**Cons:** Static — set once at startup, cannot be dynamically updated per-tool-call. Would need server restart to change. Not suitable for per-query context injection.
**Complexity:** Low
**Time Estimate:** 30 minutes (but doesn't solve the actual problem)

#### Approach 1B: Monkey-patch `call_tool` to prepend context in response (Enhanced Current)
**Description:** The current approach already monkey-patches `mcp.call_tool`. Instead of appending context to the string result, we can format the context as a structured prefix that the LLM will interpret as system-like instructions. The return type of `call_tool` is `Sequence[ContentBlock] | dict[str, Any]`, so we can return a `TextContent` block with context first, then the actual result.

**Pros:** Per-query dynamic context, no new dependencies, works with current monkey-patch pattern, context delivered before tool result.
**Cons:** Not truly a "system prompt" — appears as tool output. LLM may or may not treat it as instructions depending on the client.
**Complexity:** Low
**Time Estimate:** 1-2 hours

#### Approach 1C: Wrap tool results with structured context blocks
**Description:** Return multiple `ContentBlock` objects from `call_tool` — first block contains `[Auto-Context]` instructions, second block contains the actual tool result. MCP protocol supports multiple content blocks per tool response. The LLM client sees context as the first content block.

**Pros:** Clean separation, MCP-protocol compliant, context appears before result in content order.
**Cons:** Requires parsing the `result` type (could be `str`, `list`, etc.). Some MCP clients may render multiple blocks oddly.
**Complexity:** Medium
**Time Estimate:** 2-3 hours

#### Approach 1D: Context in tool arguments (pre-call injection)
**Description:** Instead of injecting context in the response, modify the tool *arguments* before the tool executes. Add a `_context` argument that the tool can use. This would require modifying every tool's signature.

**Pros:** Context available during tool execution, tools can use it directly.
**Cons:** Invasive — requires modifying every tool function. Breaks existing API. Not compatible with external MCP clients.
**Complexity:** High
**Time Estimate:** 4+ hours (not recommended)

### Research Area 2: Semantic Intent Classification with sentence-transformers

#### Approach 2A: Pre-computed Intent Centroids (Recommended)
**Description:** Embed a small set of canonical intent phrases at startup, cache the embeddings, then classify by comparing the user query's embedding against these centroids using cosine similarity.

```python
# Pre-computed at startup (~5ms each, one-time cost)
CHAT_CENTROIDS = [
    embed("what did we discuss previously"),
    embed("remember what was said"),
    embed("our conversation about"),
]
FILE_CENTROIDS = [
    embed("which files changed"),
    embed("import dependencies"),
    embed("file structure impact"),
]

# Classification: embed query once, compare against all centroids
query_embedding = embed(user_query)
chat_score = max(cosine_sim(query_embedding, c) for c in CHAT_CENTROIDS)
file_score = max(cosine_sim(query_embedding, c) for c in FILE_CENTROIDS)
intent = "chat" if chat_score > file_score else "file"
```

**Pros:** Zero new dependencies, uses existing `SentenceTransformerEmbeddingFunction` model, ~10-50ms latency (one embedding call + simple math), no network calls, works offline, easy to tune by adding/removing centroid phrases.
**Cons:** Manual centroid selection requires testing. May misclassify ambiguous queries (mitigated by "both" fallback).
**Complexity:** Low
**Time Estimate:** 1-2 hours

#### Approach 2B: Keyword-based classification
**Description:** Simple regex/keyword matching against predefined word lists for chat vs file intent.

**Pros:** Near-zero latency, trivial to implement, no ML needed.
**Cons:** Rejected per 6-CONTEXT.md decision. User wants semantic understanding. "tell me about the code we discussed" contains "code" (file keyword) but is actually chat intent. Keyword matching fails these cases.
**Complexity:** Low
**Time Estimate:** 30 minutes (but doesn't meet requirements)

#### Approach 2C: Fine-tuned classifier model
**Description:** Train a small text classifier (e.g., scikit-learn SGDClassifier) on labeled examples of chat vs file queries.

**Pros:** Potentially higher accuracy than centroid matching.
**Cons:** Rejected. Requires training data, adds `scikit-learn` dependency, over-engineered for a binary classification task. Centroid approach achieves ~90%+ accuracy for this narrow domain.
**Complexity:** Medium
**Time Estimate:** 3-4 hours (not recommended)

### Research Area 3: ChromaDB Multi-Document Collection

#### Approach 3A: Single Collection with Type Metadata (Recommended)
**Description:** Use the existing `chat_history` collection but store both chat messages and file change documents in it. Differentiate by `type` metadata field. Query with `where={"type": "chat"}` or `where={"type": "file_change"}` filters. Semantic search across both types simultaneously by omitting the type filter.

```python
# File change document stored in same collection
collection.add(
    ids=["fc_" + uuid.uuid4().hex],
    documents=["Modified src/context.py: added HybridContextBuilder class"],
    metadatas=[{
        "type": "file_change",
        "file_path": "src/context.py",
        "change_type": "modified",
        "symbols_added": "HybridContextBuilder",
        "snippet": "class HybridContextBuilder:",
        "timestamp": "2024-01-01T00:00:00",
    }],
)

# Query only chat messages
collection.query(query_texts=[q], where={"type": "chat"}, n_results=5)

# Query only file changes
collection.query(query_texts=[q], where={"type": "file_change"}, n_results=5)

# Query everything (hybrid semantic search)
collection.query(query_texts=[q], n_results=10)
```

**Pros:** Single collection = single embedding function = unified semantic space. ChromaDB handles all filtering. No new persistence layer. Simple architecture. Existing `query_messages()` already supports `where` clauses via `_build_where()`.
**Cons:** Collection grows faster (file changes add documents). May need periodic pruning. Existing messages don't have `type` field (need migration or default handling).
**Complexity:** Low
**Time Estimate:** 2-3 hours

#### Approach 3B: Separate ChromaDB Collections
**Description:** Create two collections: `chat_history` and `file_changes`. Query both in parallel and merge results in Python.

**Pros:** Clean separation, independent lifecycle management.
**Cons:** Two embedding computations per query (2x latency). Manual result merging and deduplication. More complex architecture. Loses ability to do unified semantic search across both types.
**Complexity:** Medium
**Time Estimate:** 3-4 hours (not recommended)

#### Approach 3C: ChromaDB + Separate JSON File
**Description:** Keep ChromaDB for chat, store file changes in `./data/file_changes.json`. Query both, merge in Python.

**Pros:** No ChromaDB schema changes.
**Cons:** Rejected per 6-CONTEXT.md decision. No semantic search on file changes. JSON doesn't scale. Manual search implementation needed. Defeats the unified storage goal.
**Complexity:** Low (but doesn't meet requirements)

### Research Area 4: FileGraph Integration for Structural Queries

#### Approach 4A: Query FileGraph Based on Intent Classification (Recommended)
**Description:** When the semantic classifier determines "file intent" or "both intent", query FileGraph for relevant structural context. Use `get_dependencies()`, `get_dependents()`, and `get_impact_set()` based on the query. Merge FileGraph results with ChromaDB results in the `HybridContextBuilder`.

```python
# In HybridContextBuilder.build():
if intent in ("file", "both"):
    # Extract file references from query (file paths or mention of files)
    mentioned_files = _extract_file_paths(query)
    if mentioned_files:
        for f in mentioned_files:
            deps = file_graph.get_dependencies(f)
            dependents = file_graph.get_dependents(f)
            # Add structural context to result
    else:
        # No specific file mentioned — return recent changes + impact summary
        recent_changes = chromadb.query(where={"type": "file_change"}, ...)
```

**Pros:** Intelligent routing — only queries FileGraph when relevant. Reuses existing FileGraph API. No new NetworkX operations needed.
**Complexity:** Medium
**Time Estimate:** 2-3 hours

#### Approach 4B: Pre-compute FileGraph Embeddings in ChromaDB
**Description:** Embed FileGraph node summaries (file paths, symbols, relationships) and store them in ChromaDB. Then semantic queries automatically find relevant files via vector similarity.

**Pros:** Unified semantic search includes structural relationships. No separate FileGraph query needed at retrieval time.
**Cons:** Stale embeddings when files change. Requires re-embedding on every graph update. Embeddings of "import relationships" don't map well to natural language queries. Complexity vs. benefit ratio is poor.
**Complexity:** High
**Time Estimate:** 4-5 hours (not recommended for Phase 6)

#### Approach 4C: FileGraph-as-Fallback Only
**Description:** Always try ChromaDB first. Only query FileGraph if ChromaDB returns fewer than N results.

**Pros:** Simple fallback logic.
**Cons:** Misses opportunities where FileGraph has relevant info but ChromaDB also has results (hybrid is better than fallback). User wants both sources combined, not fallback.
**Complexity:** Low
**Time Estimate:** 1 hour (doesn't meet hybrid requirement)

## Recommended Approach

**Selected Combination:** 1B (Enhanced Monkey-patch) + 2A (Intent Centroids) + 3A (Single Collection) + 4A (Intent-based FileGraph Querying)

### Why This Combination

1. **Zero new dependencies** — uses existing `sentence-transformers`, ChromaDB, NetworkX.
2. **Minimal invasiveness** — enhances existing monkey-patch pattern rather than rewriting server architecture.
3. **Unified storage** — single ChromaDB collection simplifies queries and maintenance.
4. **Semantic intelligence** — intent centroids understand query meaning, not just keywords.
5. **Modular** — each component can be tested independently.

### Implementation Plan

#### Step 1: Fix Query Extraction in `_wire_interception`
The critical bug: `query=name` passes the tool name. Fix by extracting the actual user query from `arguments`:

```python
# Current (broken):
context_block = _context_injector.inject(query=name, session_id=session_id)

# Fixed: extract query from tool arguments
user_query = _extract_query_from_arguments(arguments)
context_block = _context_injector.inject(query=user_query, session_id=session_id)

def _extract_query_from_arguments(arguments: dict) -> str:
    """Extract the most relevant query string from tool arguments."""
    # Priority: query > conversation > search > text > content
    for key in ("query", "conversation", "search", "text", "content"):
        if key in arguments and isinstance(arguments[key], str):
            return arguments[key]
    # Fallback: join all string values
    return " ".join(str(v) for v in arguments.values()) if arguments else ""
```

#### Step 2: Create `IntentClassifier` using sentence-transformers
```python
class IntentClassifier:
    """Semantic intent classification using pre-computed centroids."""
    
    INTENT_CHAT = [
        "what did we discuss previously",
        "remember what was said in our conversation",
        "what did I ask before",
        "tell me about our previous discussion",
    ]
    INTENT_FILE = [
        "which files changed recently",
        "what are the import dependencies",
        "show me the file structure",
        "what files are affected by this change",
    ]
    
    def __init__(self, embedding_fn):
        self._ef = embedding_fn
        self._chat_centroids = self._embed_batch(self.INTENT_CHAT)
        self._file_centroids = self._embed_batch(self.INTENT_FILE)
    
    def classify(self, query: str) -> Literal["chat", "file", "both", "unknown"]:
        q_emb = self._ef([query])[0]
        chat_score = max(self._cosine_sim(q_emb, c) for c in self._chat_centroids)
        file_score = max(self._cosine_sim(q_emb, c) for c in self._file_centroids)
        
        threshold = 0.5  # Tunable
        is_chat = chat_score > threshold
        is_file = file_score > threshold
        
        if is_chat and is_file:
            return "both"
        elif is_chat:
            return "chat"
        elif is_file:
            return "file"
        else:
            return "both"  # Safe fallback
```

#### Step 3: Add File Change Documents to ChromaDB
Extend `ChatStore` with a `store_file_change()` method. Add `type` metadata to distinguish document types:

```python
def store_file_change(self, file_change: dict, session_id: str | None = None) -> dict:
    """Store a file change document in the same collection as chat messages."""
    # Add type="file_change" to metadata
    doc = f"{file_change['change_type']} {file_change['file_path']}: {file_change.get('snippet', '')}"
    metadata = {
        "type": "file_change",
        "file_path": file_change["file_path"],
        "change_type": file_change["change_type"],
        "symbols": file_change.get("symbols", ""),
        "timestamp": file_change.get("timestamp", now),
    }
    self._collection.add(ids=[uid], documents=[doc], metadatas=[metadata])
```

Also need to backfill existing chat messages with `type="chat"` metadata:
```python
def _ensure_chat_type_metadata(self):
    """Add type='chat' to existing messages that don't have it."""
    result = self._collection.get(include=["metadatas"])
    updates_needed = []
    for i, meta in enumerate(result["metadatas"]):
        if "type" not in meta:
            updates_needed.append(result["ids"][i])
    if updates_needed:
        # ChromaDB doesn't support bulk metadata update — need to handle carefully
        # Option: only set on new documents, treat missing type as "chat" in queries
        pass
```

#### Step 4: Rewrite `HybridContextBuilder`
Replace the stub `ContextBuilder.build()` with actual hybrid retrieval:

```python
class HybridContextBuilder:
    def __init__(self, store: ChatStore, file_graph: FileGraph, classifier: IntentClassifier):
        self.store = store
        self.file_graph = file_graph
        self.classifier = classifier
    
    def build(self, query: str, session_id: str | None = None, 
              active_files: list[str] | None = None) -> ContextWindow:
        # 1. Classify intent
        intent = self.classifier.classify(query)
        
        parts = []
        sources = []
        
        # 2. Retrieve from ChromaDB based on intent
        if intent in ("chat", "both"):
            chat_results = self.store.query_messages(query, top_k=5, session_id=session_id)
            if chat_results:
                parts.append(format_with_detail({"query": query, "results": chat_results}, "summary"))
                sources.append("chat_history")
        
        if intent in ("file", "both"):
            file_results = self.store.query_messages(query, top_k=5, role=None, session_id=None)
            # Filter to file_change type in Python (ChromaDB where clause)
            file_changes = [r for r in file_results if r.get("type") == "file_change"]
            if file_changes:
                parts.append(self._format_file_changes(file_changes))
                sources.append("file_changes")
            
            # Query FileGraph for structural context
            if active_files:
                for f in active_files:
                    deps = self.file_graph.get_dependencies(f)
                    if deps:
                        parts.append(f"Dependencies of {os.path.basename(f)}: {', '.join(os.path.basename(d) for d in deps)}")
                        sources.append("file_graph")
        
        content = "\n---\n".join(parts) if parts else f"No relevant context found for: {query}"
        
        return ContextWindow(
            content=content,
            token_count=_estimate_tokens(content),
            max_tokens=4000,
            sources=sources,
        )
```

#### Step 5: Enhanced ContextInjector
Update `ContextInjector` to use `HybridContextBuilder` and return structured context blocks:

```python
class ContextInjector:
    def inject(self, query: str, session_id: str | None = None) -> str:
        if not self._enabled:
            return ""
        # Use HybridContextBuilder instead of direct ChromaDB query
        context_window = self.builder.build(query=query, session_id=session_id)
        if context_window.token_count == 0:
            return ""
        return f"[Auto-Context]\n{context_window.content}\n[Sources: {', '.join(context_window.sources)}]"
```

## Implementation Notes

### Critical Bug Fix (Highest Priority)
The single most impactful fix: `_extract_query_from_arguments()` in `mcp_server.py`. This one change makes auto-retrieve work for the first time. Current behavior searches ChromaDB for tool names like `"query_chat"` instead of actual queries like `"how does vector search work"`.

### Migration Strategy for Existing ChromaDB Data
Existing chat messages lack the `type` metadata field. Two options:
1. **Treat missing `type` as `"chat"`** — simplest, no migration needed. In `_build_where()`, add logic: `WHERE (type = 'chat' OR type IS MISSING)`.
2. **Backfill with metadata update** — ChromaDB doesn't support `collection.update()` with metadata-only. Would need to export, delete, re-import. Too risky for existing data.

**Recommended:** Option 1. When storing new documents, always include `type`. When querying chat messages, use `where={"type": "chat"}` OR fall back to `role`-based filtering for backward compatibility.

### Token Budget Enforcement
The existing `ContextInjector` enforces a ~300 token budget (`auto_context_tokens`). The hybrid builder should respect this:
- Split budget: 60% chat context, 40% file context (adjustable).
- Use `ContextWindow.fits()` to check before adding each section.
- Truncate file change snippets if over budget.

### Cosine Similarity with ChromaDB's Embedding Function
ChromaDB uses `SentenceTransformerEmbeddingFunction` which returns numpy arrays. Cosine similarity can be computed with numpy:

```python
import numpy as np

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

**Important:** This adds `numpy` as a direct import (it's already a transitive dependency of sentence-transformers, so no new package install needed).

### File Change Hook Points
File changes should be captured at three points:
1. **AutoSave middleware** — when `on_tool_response` captures file modification results.
2. **FileWatcher callback** — when `on_modified`/`on_created`/`on_deleted` fires.
3. **Manual API** — `store_file_change()` for explicit file change recording.

The FileWatcher already calls `graph.update_graph()`. We can hook into this to also store a ChromaDB document.

### Windows-Specific Risk: ChromaDB File Locks
ChromaDB uses SQLite internally. On Windows, file locks can prevent concurrent access. The `ChatStore.close()` method already handles this. Ensure `store_file_change()` doesn't hold locks across operations.

## Libraries/Tools

| Library | Why | Status |
|---------|-----|--------|
| `sentence-transformers` (all-MiniLM-L6-v2) | Intent classification embeddings | Already installed |
| `chromadb` | Unified storage for chat + file changes | Already installed |
| `networkx` | File relationship graph queries | Already installed |
| `numpy` | Cosine similarity computation | Transitive dependency (no install needed) |

## Pitfalls to Avoid

1. **Don't re-embed intent centroids on every query** — compute once at startup, cache in `IntentClassifier.__init__`.
2. **Don't store large code snippets in ChromaDB** — limit snippets to ~200 chars to keep embedding quality high and storage manageable.
3. **Don't query FileGraph for every auto-retrieve** — only query when intent classifier indicates file intent, or when active files are provided.
4. **Don't break existing `query_messages()` API** — the `get_context` tool and `query_chat` tool call this method. Add new methods for file-change-specific queries rather than changing existing signatures.
5. **Don't forget ChromaDB's `where` clause limitations** — ChromaDB v1.5.7 doesn't support `$or` on string metadata reliably. Use Python post-filtering for complex conditions.
6. **Watch for embedding function threading issues** — `SentenceTransformerEmbeddingFunction` may not be thread-safe. Ensure `IntentClassifier.classify()` is called from the async event loop only (same thread as MCP server).
7. **Don't duplicate the monkey-patch** — the existing `_wire_interception` in `mcp_server.py` is complex. Modify it carefully rather than creating a second interception layer.

## Codebase Patterns to Follow

- **Singleton pattern** — All modules use `get_store()`, `get_graph()`, `get_config()` pattern. New `IntentClassifier` and `HybridContextBuilder` should follow this.
- **Register pattern** — Each domain module exposes `register(mcp: FastMCP)`. New functionality should register its tools the same way.
- **Module-level `_build_where()` helper** — ChromaDB query building uses this pattern. Extend it for `type` filtering.
- **Session index pattern** — JSON file for O(1) lookups. Consider if file changes need similar indexing.
- **Test isolation** — All tests use `tmp_path` for isolated ChromaDB instances. New tests must follow this.
- **Existing `_estimate_tokens()` and `format_with_detail()`** — Reuse from `context.py` rather than re-implementing.
- **Config dataclass** — New config options (centroid threshold, budget split) should extend `AutoConfig`.

## Potential Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Intent classifier misclassifies queries | Medium | Medium | Use "both" as safe fallback. Tune centroids with real queries. |
| ChromaDB collection grows too large | Medium | Low | Add `prune_file_changes()` method. Set retention policy. |
| Embedding latency adds noticeable delay | Low | Low | Single query embedding is ~10-50ms. Centroid comparison is <1ms. |
| Monkey-patch breaks with FastMCP updates | High | Low | Pin FastMCP version. Add integration test that verifies monkey-patch. |
| Windows file lock conflicts with ChromaDB | High | Medium | Ensure `close()` is always called. Use try/finally in all DB operations. |
| Existing tests break due to new `type` metadata | Medium | Medium | Treat missing `type` as `"chat"` in queries. Update test fixtures. |

## Estimated Complexity by Area

| Area | Complexity | Time Estimate |
|------|-----------|---------------|
| Fix query extraction (mcp_server.py) | Low | 30 min |
| IntentClassifier class | Low | 1-2 hours |
| ChromaDB file change storage | Low-Medium | 2-3 hours |
| HybridContextBuilder rewrite | Medium | 3-4 hours |
| Enhanced ContextInjector | Low | 1 hour |
| Tests for all new components | Medium | 3-4 hours |
| **Total** | **Medium** | **10-14 hours** |
