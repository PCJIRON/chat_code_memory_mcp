# Context Memory MCP Server — Roadmap

## Overview

| | |
|---|---|
| **Total Phases** | 4 |
| **Estimated Duration** | 2–3 days (weekend) |
| **MVP** | Phase 1 + Phase 2 |
| **Total Plans** | ~18 |
| **Target Commits** | ~18 (one per task) |

### Requirement Priority Map

| Priority | Requirements | Phase |
|---|---|---|
| **P0 (Must-have)** | FR-1.1–1.4, FR-5.1, FR-5.3 | Phase 1–2 |
| **P0 (Must-have)** | FR-2.1–2.3, FR-5.2 (store_chat, query_chat) | Phase 2 |
| **P1 (Should-have)** | FR-3.1–3.4, FR-5.2 (track_files, get_file_graph) | Phase 3 |
| **P1 (Should-have)** | FR-4.1–4.3, FR-2.4 (date filter) | Phase 4 |
| **P2 (Nice-to-have)** | NFR-2 parallel parsing, watchdog | Phase 4 |

### Dependency Graph

```
Phase 1: Foundation ──→ Phase 2: Chat Memory ──→ Phase 4: Integration & Polish
                          │                           ↑
                          └──→ Phase 3: File Graph ───┘
```

Phase 2 and Phase 3 are **independent** and can be worked on in parallel (separate waves).

---

## Phase 1: Foundation

**Theme:** Project scaffold, dependencies, basic MCP server skeleton
**Goal:** A runnable FastMCP server with stdio transport and project structure in place
**Estimated Duration:** 2–3 hours
**Success Criteria:** `python -m context_memory_mcp` starts and responds to `--help` and a ping tool call

| Task | Requirement | Commit Title |
|---|---|---|
| 1.1 Create project layout: `src/`, `tests/`, `pyproject.toml` per TR-3 | TR-3 | `[GSD-1-01-T1] scaffold project layout with pyproject.toml` |
| 1.2 Add dependencies: `fastmcp`, `chromadb`, `sentence-transformers`, `tree-sitter-language-pack`, `networkx` | TR-1 | `[GSD-1-01-T2] add dependencies to pyproject.toml` |
| 1.3 Create `src/__main__.py` CLI entry point with `python -m` support | FR-5.3 | `[GSD-1-01-T3] add python -m entry point` |
| 1.4 Create `src/cli.py` with `argparse` CLI (start/stop/status commands) | FR-5.3 | `[GSD-1-01-T4] add CLI interface with argparse` |
| 1.5 Create `src/mcp_server.py` with FastMCP stdio server + `ping` tool | FR-5.1 | `[GSD-1-01-T5] create FastMCP server with ping tool` |
| 1.6 Create placeholder modules: `chat_store.py`, `file_graph.py`, `parser.py`, `embeddings.py`, `context.py` | TR-3 | `[GSD-1-01-T6] create placeholder modules` |

**Phase 1 Deliverable:** A working MCP server that starts, responds to `ping`, and has all module stubs in place.

---

## Phase 2: Chat Memory

**Theme:** ChromaDB integration, local embeddings, store/query tools
**Goal:** Full chat history persistence with semantic search
**Estimated Duration:** 4–6 hours
**Success Criteria:** Messages stored via MCP tool → survive restart → retrieved by semantic similarity with correct role/timestamp

| Task | Requirement | Commit Title |
|---|---|---|
| 2.1 Create `src/embeddings.py`: local sentence-transformers wrapper with configurable model | FR-1.3, TR-1 | `[GSD-2-01-T1] implement local embedding wrapper with sentence-transformers` |
| 2.2 Create `src/chat_store.py`: ChromaDB init with persistent storage (local path, not in-memory) | FR-1.4, NFR-1 | `[GSD-2-01-T2] initialize ChromaDB with persistent local storage` |
| 2.3 Implement `store_message(content, role, conversation_id)` in `chat_store.py` — embed + store with metadata | FR-1.1, FR-1.2 | `[GSD-2-01-T3] implement store_message with metadata` |
| 2.4 Implement `batch_store_messages(messages)` for bulk ingestion | FR-1.1 | `[GSD-2-01-T4] implement batch_store_messages` |
| 2.5 Implement `query_messages(query, top_k=5)` — semantic similarity search using embeddings | FR-2.1, FR-2.2 | `[GSD-2-01-T5] implement semantic query_messages with top-K` |
| 2.6 Implement `query_with_filter(query, top_k, role, date_range)` — add metadata filtering | FR-2.3, FR-2.4 | `[GSD-2-01-T6] add metadata filtering to query_messages` |
| 2.7 Register `store_chat` MCP tool in `mcp_server.py` — delegates to `chat_store.store_message` | FR-5.2 | `[GSD-2-01-T7] register store_chat MCP tool` |
| 2.8 Register `query_chat` MCP tool in `mcp_server.py` — delegates to `chat_store.query_messages` | FR-5.2 | `[GSD-2-01-T8] register query_chat MCP tool` |
| 2.9 End-to-end test: start server → store message → restart → query message → verify results | FR-1.4 | `[GSD-2-01-T9] add e2e test for chat storage persistence` |

**Phase 2 Deliverable:** Fully functional chat memory — store, persist, and semantically retrieve conversation history. **This completes MVP.**

---

## Phase 3: File Graph

**Theme:** AST parsing with tree-sitter, NetworkX graph, SHA-256 change tracking
**Goal:** Parse file relationships, build graph, detect changes, incremental updates
**Estimated Duration:** 4–6 hours
**Success Criteria:** Given a Python project directory, the server builds a graph of imports/calls/dependencies and detects which files changed via SHA-256

| Task | Requirement | Commit Title |
|---|---|---|
| 3.1 Create `src/parser.py`: tree-sitter AST parser — extract imports, classes, functions from a single file | FR-3.1, TR-2 | `[GSD-3-01-T1] implement tree-sitter AST parser for single file` |
| 3.2 Implement `parse_file_to_nodes(file_path)` — emit qualified names (`/path/file.py::ClassName.method_name`) | FR-3.1, TR-2 | `[GSD-3-01-T2] implement parse_file_to_nodes with qualified names` |
| 3.3 Implement `extract_edges(file_tree)` — CALLS, IMPORTS_FROM, INHERITS, DEPENDS_ON edge types | FR-3.1, TR-2 | `[GSD-3-01-T3] implement edge extraction (CALLS, IMPORTS_FROM, INHERITS, DEPENDS_ON)` |
| 3.4 Create `src/file_graph.py`: NetworkX graph init — `add_node`, `add_edge`, `get_subgraph(file_path)` | FR-3.3, TR-2 | `[GSD-3-01-T4] initialize NetworkX file graph with CRUD operations` |
| 3.5 Implement `build_graph(directory)` — walk dir, parse each file, populate graph | FR-3.3 | `[GSD-3-01-T5] implement build_graph for directory walk` |
| 3.6 Implement SHA-256 change detection: `compute_file_hash(path)`, `detect_changes(directory, index)` | FR-3.2 | `[GSD-3-01-T6] implement SHA-256 change detection` |
| 3.7 Implement incremental update: `update_graph(directory, changed_files)` — only re-parse changed files | FR-3.4 | `[GSD-3-01-T7] implement incremental graph update` |
| 3.8 Persist graph to disk: `save_graph(path)`, `load_graph(path)` using NetworkX GML or GraphML | FR-3.4 | `[GSD-3-01-T8] add graph persistence to disk` |
| 3.9 Register `track_files(directory)` MCP tool — build/update graph and return summary | FR-5.2 | `[GSD-3-01-T9] register track_files MCP tool` |
| 3.10 Register `get_file_graph(file_path)` MCP tool — return subgraph for a specific file | FR-5.2 | `[GSD-3-01-T10] register get_file_graph MCP tool` |

**Phase 3 Deliverable:** File relationship graph — parse, build, track changes, and query via MCP tools.

---

## Phase 4: Integration & Polish

**Theme:** Token-efficient context retrieval, date filtering, end-to-end testing
**Goal:** Minimize token output, optimize retrieval for LLM consumption, full integration test
**Estimated Duration:** 2–4 hours
**Success Criteria:** `get_minimal_context` returns ~100 tokens, all 5 MCP tools work end-to-end, no errors

| Task | Requirement | Commit Title |
|---|---|---|
| 4.1 Create `src/context.py`: implement `get_minimal_context(messages)` — compress to ~100 tokens | FR-4.1, FR-4.3 | `[GSD-4-01-T1] implement get_minimal_context compression` |
| 4.2 Implement `format_with_detail(messages, detail_level)` — minimal/summary/full output modes | FR-4.2 | `[GSD-4-01-T2] implement detail_level formatting (minimal/summary/full)` |
| 4.3 Register `get_context` MCP tool with `detail_level` parameter | FR-4.2, FR-5.2 | `[GSD-4-01-T3] register get_context MCP tool with detail_level` |
| 4.4 Add `conversation_id` parameter to `query_chat` tool for filtering by conversation | FR-2.4 | `[GSD-4-01-T4] add conversation_id filter to query_chat` |
| 4.5 Add `date_from`/`date_to` parameters to `query_chat` tool for date range filtering | FR-2.4 | `[GSD-4-01-T5] add date range filter to query_chat` |
| 4.6 Write `tests/test_chat_store.py` — unit tests for store/query/filter | FR-1, FR-2 | `[GSD-4-01-T6] add unit tests for chat_store` |
| 4.7 Write `tests/test_file_graph.py` — unit tests for graph build/update/detect | FR-3 | `[GSD-4-01-T7] add unit tests for file_graph` |
| 4.8 End-to-end integration test: start server → all 5 tools → verify outputs | FR-5.2 | `[GSD-4-01-T8] add end-to-end integration test for all MCP tools` |
| 4.9 Write `README.md` — setup, usage, tool descriptions, examples | — | `[GSD-4-01-T9] write README with setup and usage docs` |

**Phase 4 Deliverable:** Token-efficient context retrieval, date/conversation filtering, test coverage, and documentation. **Project complete.**

---

## Milestones

| Milestone | Trigger | Expected |
|---|---|---|
| **M1: Server Runs** | Phase 1 complete — `python -m` starts, ping responds | Day 1, morning |
| **M2: MVP** | Phase 2 complete — store + query chat messages with persistence | Day 1, evening |
| **M3: File Graph** | Phase 3 complete — parse, build, track, query file relationships | Day 2, evening |
| **M4: Ship** | Phase 4 complete — all tools tested, token-efficient, documented | Day 3 |

---

## Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | `sentence-transformers` model download is slow or fails offline | Blocks Phase 2 | Pre-download model in Phase 1; use small model (`all-MiniLM-L6-v2`) |
| R2 | `tree-sitter-language-pack` installation fails on Windows | Blocks Phase 3 | Fall back to Python-only parsing for imports/classes; defer function-level parsing to post-MVP |
| R3 | ChromaDB persistent storage not working correctly | Data loss risk | Test persistence explicitly in task 2.9; use explicit `persist_directory` |
| R4 | Feature creep — adding Leiden, D3, multi-user, cloud APIs | Blows weekend scope | Enforce "Out of Scope" list in REQUIREMENTS.md; defer to Phase 5+ only |
| R5 | FastMCP stdio transport quirks on Windows | Blocks all MCP tools | Test with simple ping tool first (Phase 1); use `stdio` not `sse` |

---

## Out of Scope (Deferred)

These are explicitly excluded from the weekend scope:
- Multi-user support / authentication
- Cloud embeddings (OpenAI, Google, etc.)
- VS Code extension
- Web visualization (D3.js)
- Community detection (Leiden algorithm)
- Execution flow analysis
- Risk scoring / refactoring tools
- Multi-repo registry
- `watchdog` file system watcher (optional, post-MVP)

---

## Execution Strategy

```
Wave 1: Phase 1 (Foundation) — sequential
Wave 2: Phase 2 (Chat Memory) + Phase 3 (File Graph) — parallel if desired, or sequential
Wave 3: Phase 4 (Integration & Polish) — sequential, depends on Phase 2 + Phase 3
```

**Recommended path:** Execute Phase 1 → Phase 2 → Phase 3 → Phase 4 sequentially over the weekend.
Phase 2 and Phase 3 are independent — if you get stuck on one, switch to the other.
