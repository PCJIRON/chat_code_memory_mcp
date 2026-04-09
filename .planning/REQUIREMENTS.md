# Requirements: Context Memory MCP Server

## 1. Project Context
An MCP server for personal use that stores chat history in ChromaDB and tracks file changes using graph/tree structures, inspired by the architecture of code-review-graph.

## 2. Functional Requirements

### FR-1: Chat History Storage
- **FR-1.1**: MCP server MUST intercept and store conversation history
- **FR-1.2**: Each message MUST be stored with metadata (timestamp, role, content)
- **FR-1.3**: Messages MUST be embedded using local sentence-transformers
- **FR-1.4**: Storage MUST be persistent (survives server restart)

### FR-2: Context Retrieval
- **FR-2.1**: Server MUST provide a tool to query chat history by semantic similarity
- **FR-2.2**: Queries MUST return top-K most relevant messages
- **FR-2.3**: Results MUST include message content, role, and timestamp
- **FR-2.4**: Server MUST support filtering by date range or conversation ID

### FR-3: File Change Tracking
- **FR-3.1**: Server MUST parse and store file relationships (imports, calls, dependencies)
- **FR-3.2**: Server MUST track changed files using SHA-256 hashing
- **FR-3.3**: Server MUST build a graph/tree structure of file relationships
- **FR-3.4**: Server MUST support incremental updates (only re-parse changed files)

### FR-4: Token Efficiency
- **FR-4.1**: Server MUST provide a `get_minimal_context` tool (~100 tokens)
- **FR-4.2**: Tools MUST support `detail_level` parameter (minimal, summary, full)
- **FR-4.3**: Retrieved context MUST be optimized for LLM consumption

### FR-5: MCP Server Interface
- **FR-5.1**: Server MUST use FastMCP with stdio transport
- **FR-5.2**: Server MUST expose tools for: store_chat, query_chat, get_context, track_files, get_file_graph
- **FR-5.3**: Server MUST support CLI entry point via `python -m`

## 3. Non-Functional Requirements

### NFR-1: Privacy
- All data MUST be stored locally (ChromaDB persistent storage)
- NO cloud API calls for embeddings or storage
- NO telemetry or external communication

### NFR-2: Performance
- Chat storage MUST complete in <500ms
- Context retrieval MUST complete in <1s
- File parsing SHOULD use parallel execution (ProcessPoolExecutor)

### NFR-3: Scope Constraints
- MVP MUST be completable in a weekend (2-3 days)
- Features MUST be minimal — no nice-to-haves in v1
- Code MUST be single-user focused (no auth/multi-user)

## 4. Technical Requirements

### TR-1: Dependencies
- `fastmcp` — MCP server framework
- `chromadb` — Vector storage
- `sentence-transformers` — Local embeddings
- `tree-sitter-language-pack` — Multi-language AST parsing
- `networkx` — Graph data structures (or SQLite recursive CTEs)
- `watchdog` — File system watching (optional for v1)

### TR-2: Data Structures
- **Chat messages**: Stored in ChromaDB collection with metadata
  - ID: UUID or hash
  - Content: message text
  - Metadata: {role, timestamp, conversation_id, file_context}
- **File graph**: Nodes (files, classes, functions) + Edges (imports, calls, depends)
  - Qualified name format: `/absolute/path/file.py::ClassName.method_name`

### TR-3: Architecture
```
mcp-server/
├── src/
│   ├── __init__.py
│   ├── __main__.py          # python -m entry
│   ├── cli.py               # CLI interface
│   ├── mcp_server.py        # FastMCP server + tool registration
│   ├── chat_store.py        # ChromaDB chat history storage
│   ├── file_graph.py        # File relationship graph
│   ├── parser.py            # Tree-sitter AST parser (from code-review-graph)
│   ├── embeddings.py        # Local embedding wrapper
│   └── context.py           # Token-efficient context retrieval
├── tests/
├── pyproject.toml
└── README.md
```

## 5. Out of Scope (v1)
- Multi-user support
- Cloud embeddings (Google, OpenAI)
- VS Code extension
- Web visualization (D3.js)
- Community detection (Leiden algorithm)
- Execution flow analysis
- Risk scoring
- Refactoring tools
- Multi-repo registry

## 6. Success Criteria
- [ ] MCP server starts and responds to tool calls
- [ ] Chat messages are stored to ChromaDB and retrievable
- [ ] File graph is built and queryable
- [ ] Context retrieval reduces token usage vs. full history
- [ ] Weekend project scope maintained (no feature creep)
