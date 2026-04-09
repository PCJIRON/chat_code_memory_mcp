"""ChromaDB-based chat history storage.

Manages persistent storage and retrieval of conversation turns
using ChromaDB vector embeddings for semantic search.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from pydantic import Field


class ChatMessage:
    """Represents a single chat message in the conversation history.

    Attributes:
        session_id: Unique identifier for the conversation session.
        message_id: Unique identifier for this message.
        role: Message role ("user", "assistant", "system").
        content: The message text content.
        timestamp: ISO 8601 timestamp of when the message was created.
        metadata: Additional metadata (token count, model used, etc.).
    """

    def __init__(
        self,
        session_id: str,
        message_id: str,
        role: str,
        content: str,
        timestamp: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a ChatMessage.

        Args:
            session_id: Unique identifier for the conversation Session.
            message_id: Unique identifier for this message.
            role: Message role ("user", "assistant", "system").
            content: The message text content.
            timestamp: ISO 8601 timestamp.
            metadata: Additional metadata dictionary.
        """
        self.session_id = session_id
        self.message_id = message_id
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize the message to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "session_id": self.session_id,
            "message_id": self.message_id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatMessage:
        """Deserialize a message from a dictionary.

        Args:
            data: Dictionary with message fields.

        Returns:
            A new ChatMessage instance.
        """
        return cls(
            session_id=data["session_id"],
            message_id=data["message_id"],
            role=data["role"],
            content=data["content"],
            timestamp=data["timestamp"],
            metadata=data.get("metadata"),
        )


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
        chroma_path: str | None = None,
    ) -> None:
        """Initialize the ChatStore.

        Args:
            collection_name: Name of the ChromaDB collection to use.
            chroma_path: Path for persistent storage. Defaults to ./data/chromadb.
        """
        self._chroma_path = chroma_path or "./data/chromadb"
        self._collection_name = collection_name
        self._client = chromadb.PersistentClient(path=self._chroma_path)
        self._ef = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )

    def close(self) -> None:
        """Close the ChromaDB client, releasing SQLite file locks (critical on Windows)."""
        self._client.close()

    def store_messages(
        self,
        messages: list[dict[str, str]],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Batch store chat messages with metadata.

        Args:
            messages: List of message dicts with "role" and "content" keys.
                      Optionally "timestamp" key (ISO 8601).
            session_id: Session UUID. Auto-generated if not provided.

        Returns:
            Dict with "stored" count and "session_id".
        """
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

        Args:
            session_id: Optional session ID filter.
            role: Optional role filter.

        Returns:
            None if no filters, single dict if one filter,
            or {"$and": [...]} if both.
        """
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

        Args:
            query: Natural language search query.
            top_k: Number of results to return.
            session_id: Optional filter to specific session.
            date_from: ISO 8601 start date (e.g. "2024-01-01T00:00:00").
            date_to: ISO 8601 end date.
            role: Optional filter by role ("user", "assistant", "system").

        Returns:
            List of result dicts with content, role, timestamp, session_id,
            distance, and similarity keys.
        """
        where = self._build_where(session_id=session_id, role=role)

        # Over-fetch to account for Python-side date filtering
        fetch_k = max(top_k * 3, 50)

        result = self._collection.query(
            query_texts=[query],
            n_results=fetch_k,
            where=where if where else None,
            include=["documents", "metadatas", "distances"],
        )

        # Results are double-nested: result["documents"] is List[List[str]]
        docs = result["documents"][0]
        metas = result["metadatas"][0]
        distances = result["distances"][0]

        filtered = []
        for i in range(len(docs)):
            ts = metas[i]["timestamp"]

            # Python-side date filtering via ISO 8601 string comparison
            if date_from and ts < date_from:
                continue
            if date_to and ts > date_to:
                continue

            dist = distances[i]
            filtered.append({
                "content": docs[i],
                "role": metas[i]["role"],
                "timestamp": ts,
                "session_id": metas[i]["session_id"],
                "distance": round(dist, 4),
                "similarity": round(1 - dist, 4),
            })

        return filtered[:top_k]

    def list_sessions(self) -> list[str]:
        """List all available conversation session IDs.

        Returns:
            Sorted list of unique session ID strings.
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
        result = self._collection.get(
            where={"session_id": session_id},
        )
        ids_to_delete = result["ids"]
        if not ids_to_delete:
            return 0
        self._collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)


# Module-level singleton for use in MCP tools
_store = ChatStore()


def register(mcp: FastMCP) -> None:
    """Register chat memory tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
    """

    @mcp.tool(
        name="store_chat",
        description="Store chat messages in conversation history",
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
        """Store a batch of chat messages with optional session ID."""
        result = _store.store_messages(messages=messages, session_id=session_id)
        return json.dumps(result, indent=2)

    @mcp.tool(
        name="query_chat",
        description="Search chat history by semantic similarity",
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
            Field(description="ISO 8601 end date"),
        ] = None,
        role: Annotated[
            str | None,
            Field(description='Filter by role: "user", "assistant", "system"'),
        ] = None,
    ) -> str:
        """Query chat history with semantic search and optional filters."""
        results = _store.query_messages(
            query=query,
            top_k=top_k,
            session_id=session_id,
            date_from=date_from,
            date_to=date_to,
            role=role,
        )
        return json.dumps(
            {
                "query": query,
                "results": results,
                "total_found": len(results),
            },
            indent=2,
        )
