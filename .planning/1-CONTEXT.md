# Phase 1 Context — Foundation

## Phase Goal
Create project scaffold, dependencies, and a runnable FastMCP server with stdio transport.

## Decisions

### Decision 1: Project Structure
- **Decision:** Use `src/` layout — `src/context_memory_mcp/` as the package directory
- **Rationale:** Standard Python packaging, cleaner separation, easier to publish later
- **Alternatives considered:** Flat layout (modules at root)
- **Trade-offs:** Slightly more complex but follows best practices

### Decision 2: Package Management
- **Decision:** Use `uv` (same as code-review-graph)
- **Rationale:** Fast, modern, already proven in code-review-graph ecosystem
- **Alternatives considered:** pip + requirements.txt, poetry
- **Trade-offs:** Requires uv installed, but much faster dependency resolution

### Decision 3: CLI Design
- **Decision:** Full CLI with subcommands — `start`, `stop`, `status`, `config`
- **Rationale:** Matches code-review-graph pattern, gives control over server lifecycle
- **Alternatives considered:** Direct `python -m` start, no subcommands
- **Trade-offs:** More boilerplate but better UX for managing server

### Decision 4: MCP Transport
- **Decision:** `stdio` only
- **Rationale:** Personal use, runs locally via Claude Desktop or similar MCP client. Simpler, no HTTP server needed.
- **Alternatives considered:** Also support `sse` (HTTP)
- **Trade-offs:** stdio is simpler but requires direct process communication; can add SSE later if needed

### Decision 5: Ping Tool Response
- **Decision:** Return server status info — `{status: "ok", version: "0.1.0", storage: "chromadb-ready"}`
- **Rationale:** More useful than just "pong", confirms server capabilities at a glance
- **Alternatives considered:** Simple "pong" string
- **Trade-offs:** Slightly more code but provides immediate diagnostic value

### Decision 6: Placeholder Module Style
- **Decision:** Follow code-review-graph style — minimal class/function signatures with docstrings
- **Rationale:** Consistent with the project's inspiration, provides clear structure for future implementation
- **Alternatives considered:** Empty files, `raise NotImplementedError`
- **Trade-offs:** Matches existing patterns, gives implementers clear guidance

## File Structure (Final)
```
context-memory-mcp/
├── src/
│   └── context_memory_mcp/
│       ├── __init__.py          # __version__ = "0.1.0"
│       ├── __main__.py          # python -m entry → cli.main()
│       ├── cli.py               # argparse CLI: start, stop, status, config
│       ├── mcp_server.py        # FastMCP stdio server + ping tool
│       ├── chat_store.py        # Placeholder: ChromaDB chat history storage
│       ├── file_graph.py        # Placeholder: File relationship graph
│       ├── parser.py            # Placeholder: Tree-sitter AST parser
│       ├── embeddings.py        # Placeholder: Local embedding wrapper
│       └── context.py           # Placeholder: Token-efficient context retrieval
├── tests/
├── pyproject.toml
└── README.md
```

## Dependencies (Phase 1)
| Package | Purpose |
|---------|---------|
| `fastmcp` | MCP server framework |
| `chromadb` | Vector storage (added to pyproject, used in Phase 2) |
| `sentence-transformers` | Local embeddings (Phase 2) |
| `tree-sitter-language-pack` | Multi-language AST parsing (Phase 3) |
| `networkx` | Graph data structures (Phase 3) |

## Testing Strategy (Phase 1)
- Manual test: `python -m context_memory_mcp start` → server starts
- Manual test: `python -m context_memory_mcp --help` → CLI help shows
- Manual test: ping tool returns status JSON
- Unit tests deferred to Phase 4

## Risks
- **R5**: FastMCP stdio transport on Windows — mitigated by testing ping tool first
- **uv availability**: User must have uv installed — will verify before proceeding
