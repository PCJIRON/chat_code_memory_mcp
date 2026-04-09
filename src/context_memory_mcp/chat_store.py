"""ChromaDB-based chat history storage.

Manages persistent storage and retrieval of conversation turns
using ChromaDB vector embeddings for semantic search.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


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
