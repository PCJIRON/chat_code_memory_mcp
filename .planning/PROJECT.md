# Context Memory MCP Server

## Project Overview
An MCP server that stores chat history and tracks file changes using ChromaDB for vector-based context memory and graph/tree structures for relationship tracking. Built for personal use to save tokens by retrieving stored context instead of re-sending it with every request.

## Problem Statement
- LLM conversations consume tokens repeatedly when context is re-sent
- No persistent memory between sessions
- File changes and their relationships are lost between coding sessions
- Need local, private storage without cloud API costs

## Solution
An MCP server using:
- **ChromaDB** for vector-based chat history storage with local embeddings
- **Graph/tree structures** (inspired by code-review-graph) to track file relationships and changes
- **FastMCP** for stdio-based MCP tool integration
- **Local sentence-transformers** for embeddings (no API costs, full privacy)

## Target User
Personal use — the developer building this project.

## MVP Features
1. **Chat History Storage**: Intercept and store all conversation history in ChromaDB
2. **Context Retrieval**: Query stored chat history by semantic similarity
3. **File Change Tracking**: Build and maintain a graph of file relationships (inspired by code-review-graph architecture)
4. **Token Savings**: Retrieve minimal context from memory instead of re-sending full history
5. **Local Embeddings**: Use sentence-transformers for zero-cost, private embeddings

## Tech Stack
- **Python** (primary language)
- **FastMCP** (MCP server framework)
- **ChromaDB** (vector storage for chat history)
- **sentence-transformers** (local embeddings)
- **NetworkX** or **SQLite recursive CTEs** (graph/tree for file relationships)
- **tree-sitter** (AST parsing for file analysis, from code-review-graph)
- **argparse** (CLI interface)

## Design Principles
- Minimal and focused (weekend project scope)
- Local-first, no cloud dependencies
- Privacy-focused (all data stays on disk)
- Reuse patterns from code-review-graph where applicable

## Key Research Findings (from code-review-graph)
- Qualified name format: `/absolute/path/file.py::ClassName.method_name`
- Edge types: CALLS, IMPORTS_FROM, INHERITS, IMPLEMENTS, CONTAINS, TESTED_BY, DEPENDS_ON
- SQLite recursive CTEs for graph traversal (or NetworkX fallback)
- SHA-256 file hashing for change detection
- Leiden algorithm for community detection
- FTS5 + vector hybrid search (we'll use ChromaDB's native search instead)
- FastMCP stdio server architecture
- Token-efficient output with `detail_level` parameter

## Scope
Weekend project — minimal viable implementation focused on core functionality.
