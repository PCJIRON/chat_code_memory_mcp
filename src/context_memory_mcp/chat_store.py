"""ChromaDB-based chat history storage.

Manages persistent storage and retrieval of conversation turns
using ChromaDB vector embeddings for semantic search.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from mcp.server.fastmcp import FastMCP
from pydantic import Field

# Module-level singleton — instantiated once at server startup
_store: ChatStore | None = None


def get_store() -> ChatStore:
    """Get or create the module-level ChatStore singleton."""
    global _store
    if _store is None:
        _store = ChatStore()
    return _store


class ChatStore:
    """Persistent chat history storage backed by ChromaDB.

    Provides methods to store, retrieve, and search chat messages
    using both exact lookups and semantic similarity search.

    Attributes:
        collection_name: Name of the ChromaDB collection.
        chroma_path: File path for the persistent ChromaDB storage.
    """

    def __init__(
        self,
        collection_name: str = "chat_history",
        chroma_path: str = "./data/chromadb",
    ) -> None:
        """Initialize the ChatStore.

        ⚠️ First instantiation of SentenceTransformerEmbeddingFunction
        downloads ~80MB model (~25s). This is expected — do not interrupt.

        Args:
            collection_name: Name of the ChromaDB collection to use.
            chroma_path: Path for persistent storage. Defaults to ./data/chromadb.
        """
        self._client = chromadb.PersistentClient(path=chroma_path)
        self._ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    def close(self) -> None:
        """Close the ChromaDB client to release SQLite file locks.

        CRITICAL on Windows: must be called before process exit.
        """
        self._client.close()

    def store_messages(
        self,
        messages: list[dict[str, str]],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Batch store chat messages with metadata.

        Each message dict must have 'role' and 'content' keys.
        Missing 'timestamp' keys are filled with the current UTC time.
        If session_id is None, a UUID is auto-generated.

        Args:
            messages: List of {role, content, timestamp?} dicts.
            session_id: Session UUID. Auto-generated if not provided.

        Returns:
            Dict with 'stored' count and 'session_id'.

        Raises:
            ValueError: If messages is empty or any message is missing 'content'.
        """
        if not messages:
            raise ValueError("messages list cannot be empty")

        for i, msg in enumerate(messages):
            if "content" not in msg:
                raise ValueError(f"Message {i} is missing required 'content' key")
            if "role" not in msg:
                msg["role"] = "user"

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

    def _build_where(
        self,
        session_id: str | None = None,
        role: str | None = None,
    ) -> dict[str, Any] | None:
        """Build ChromaDB where clause from optional filters.

        Returns None if no filters, single dict if one filter,
        or {'$and': [...]} if multiple filters.
        """
        conditions: list[dict[str, Any]] = []
        if session_id:
            conditions.append({"session_id": session_id})
        if role:
            conditions.append({"role": role})
        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def query_messages(
        self,
        query: str,
        top_k: int = 5,
        session_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query chat history by semantic similarity with optional filters.

        Date filtering is done in Python after fetching results because
        ChromaDB v1.5.7 does not support $gte/$lte on string metadata.
        We over-fetch with n_results=max(top_k*3, 50) and then filter
        + slice to top_k.

        Args:
            query: Natural language search query.
            top_k: Number of results to return.
            session_id: Filter to specific session.
            date_from: ISO 8601 start date (e.g. 2024-01-01T00:00:00).
            date_to: ISO 8601 end date.
            role: Filter by role ("user", "assistant", "system").

        Returns:
            List of result dicts with content, role, timestamp, distance, similarity.
        """
        where = self._build_where(session_id=session_id, role=role)

        # Over-fetch to have enough candidates for Python date filtering
        n_results = max(top_k * 3, 50)

        result = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        # ChromaDB returns double-nested lists: result["documents"] is List[List[str]]
        docs = result["documents"][0]
        metas = result["metadatas"][0]
        dists = result["distances"][0]

        # Apply date filtering in Python (ISO 8601 strings compare lexicographically)
        filtered: list[dict[str, Any]] = []
        for i in range(len(docs)):
            ts = metas[i]["timestamp"]
            if date_from and ts < date_from:
                continue
            if date_to and ts > date_to:
                continue
            distance = dists[i]
            filtered.append({
                "content": docs[i],
                "role": metas[i]["role"],
                "timestamp": ts,
                "session_id": metas[i]["session_id"],
                "distance": round(distance, 4),
                "similarity": round(1 - distance, 4),
            })

        return filtered[:top_k]

    def list_sessions(self) -> list[str]:
        """List all available conversation session IDs.

        Returns:
            Sorted list of distinct session IDs.
        """
        result = self._collection.get(include=["metadatas"])
        session_ids = set()
        for meta in result["metadatas"]:
            session_ids.add(meta["session_id"])
        return sorted(session_ids)

    def delete_session(self, session_id: str) -> int:
        """Delete all messages from a specific session.

        Args:
            session_id: The session to delete.

        Returns:
            Number of messages deleted.
        """
        result = self._collection.get(where={"session_id": session_id})
        ids_to_delete = result["ids"]
        if not ids_to_delete:
            return 0
        self._collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)


def register(mcp: FastMCP) -> None:
    """Register chat memory tools with the MCP server.

    Registers:
        store_chat — Batch store chat messages
        query_chat — Semantic search with optional filters
    """
    store = get_store()

    @mcp.tool(
        name="store_chat",
        description="Store a batch of chat messages in conversation history",
    )
    async def store_chat(
        messages: Annotated[
            list[dict[str, str]],
            Field(description='List of {role: "user"|"assistant"|"system", content: str} objects'),
        ],
        session_id: Annotated[
            str | None,
            Field(description="Session UUID. Auto-generated if omitted"),
        ] = None,
    ) -> str:
        """Store chat messages with metadata. Returns JSON with stored count and session_id."""
        result = store.store_messages(messages=messages, session_id=session_id)
        return json.dumps(result, indent=2)

    @mcp.tool(
        name="query_chat",
        description="Search chat history by semantic similarity with optional filters",
    )
    async def query_chat(
        query: Annotated[
            str,
            Field(description="Natural language search query"),
        ],
        top_k: Annotated[
            int,
            Field(description="Number of results to return", ge=1, le=50),
        ] = 5,
        session_id: Annotated[
            str | None,
            Field(description="Filter to specific session"),
        ] = None,
        date_from: Annotated[
            str | None,
            Field(description="ISO 8601 start date (e.g. 2024-01-01T00:00:00)"),
        ] = None,
        date_to: Annotated[
            str | None,
            Field(description="ISO 8601 end date (e.g. 2024-01-31T23:59:59)"),
        ] = None,
        role: Annotated[
            str | None,
            Field(description='Filter by role: "user", "assistant", "system"'),
        ] = None,
    ) -> str:
        """Query chat history with semantic search and optional filters."""
        results = store.query_messages(
            query=query,
            top_k=top_k,
            session_id=session_id,
            date_from=date_from,
            date_to=date_to,
            role=role,
        )
        return json.dumps({
            "query": query,
            "total_found": len(results),
            "results": results,
        }, indent=2)
