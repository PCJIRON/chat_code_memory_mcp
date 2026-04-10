# QWEN.md - Project Instructions & MCP Memory Rules

## MCP Memory Protocol (MANDATORY)

### Every Chat: Store + Retrieve
- **After every response**, call `mcp__context-memory-mcp__store_chat` with the current conversation turn (user message + assistant response)
- **Immediately after storing**, call `mcp__context-memory-mcp__query_chat` with `query="recent conversation context"` and `top_k=5`
- Use retrieved context to refresh your memory before next response
- No counter needed — every chat is fully persisted and refreshed

## Available MCP Tools (Use in This Sequence)

### 1. `mcp__context-memory-mcp__ping`
- **Purpose**: Check if MCP server is running
- **When to use**: At session start, or if any MCP tool fails
- **Params**: None

### 2. `mcp__context-memory-mcp__store_chat`
- **Purpose**: Save conversation to persistent memory
- **When to use**: **After every single chat exchange** (mandatory)
- **Params**:
  - `messages`: List of `{role: "user"|"assistant", content: "..."}` objects
  - `session_id`: Optional (auto-generated if omitted)

### 3. `mcp__context-memory-mcp__query_chat`
- **Purpose**: Retrieve past conversation context
- **When to use**: **Every chat** (after store), or when user asks about previous discussions
- **Params**:
  - `query`: Search query (natural language)
  - `top_k`: Number of results (1-50, default 5)
  - `session_id`: Optional filter
  - `date_from`, `date_to`: Optional ISO 8601 date filters
  - `role`: Optional filter by role ("user", "assistant", "system")

### 4. `mcp__context-memory-mcp__get_context`
- **Purpose**: Get token-efficient context for a specific query
- **When to use**: When you need focused context on a topic, not full chat history
- **Params**:
  - `query`: Search query (required)
  - `detail_level`: "minimal" | "summary" | "full" (default: "summary")
  - `session_id`: Optional
  - `active_files`: Optional list of file paths

### 5. `mcp__context-memory-mcp__track_files`
- **Purpose**: Build/update file relationship graph for a directory
- **When to use**: When user asks about project structure, or before `get_file_graph`
- **Params**:
  - `directory`: Absolute path to scan

### 6. `mcp__context-memory-mcp__get_file_graph`
- **Purpose**: Get file relationship subgraph for a specific file
- **When to use**: After `track_files`, when analyzing file dependencies
- **Params**:
  - `file_path`: Absolute path to file

## Execution Rules

1. **ALWAYS** store chat after every response — no exceptions
2. **ALWAYS** retrieve context after every store — refresh memory automatically
3. **Ping MCP** at session start to verify connectivity
4. **Never skip** store/retrieve steps even for short responses
5. **Workflow**: Store → Retrieve → Respond

## Workflow Example

```
User: "hello"
Assistant: "Hi! How can I help?"
→ STORE chat
→ RETRIEVE context (top_k=5)
→ Ready for next chat with full context

User: "what did I just ask?"
→ STORE chat
→ RETRIEVE context (top_k=5)
→ "You asked about..."
```

## Language Preference
- User prefers **Hindi/Hinglish** for casual conversation
- Technical artifacts, code, and commands remain in **English**
- Follow output-language.md: Respond in English unless user requests otherwise

## Project Context
- **Project Type**: Python project with GSD (Get Shit Done) workflow
- **Key Directories**: `.planning/`, `src/`, `tests/`, `scripts/`, `data/`
- **Config**: `pyproject.toml`
