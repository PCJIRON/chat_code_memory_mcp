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

    def add_message(self, message: ChatMessage) -> str:
        """Store a chat message in ChromaDB.

        Args:
            message: The ChatMessage to store.

        Returns:
            The document ID of the stored message.
        """
        ...

    def get_session_messages(self, session_id: str, limit: int = 100) -> list[ChatMessage]:
        """Retrieve all messages from a specific session.

        Args:
            session_id: The session to retrieve messages from.
            limit: Maximum number of messages to return.

        Returns:
            List of ChatMessage objects, ordered by timestamp.
        """
        ...

    def search_similar(
        self,
        query: str,
        session_id: str | None = None,
        top_k: int = 5,
    ) -> list[ChatMessage]:
        """Search for semantically similar messages.

        Args:
            query: The search query text.
            session_id: Optional filter to a specific session.
            top_k: Number of results to return.

        Returns:
            List of ChatMessage objects sorted by similarity.
        """
        ...

    def delete_session(self, session_id: str) -> int:
        """Delete all messages from a specific session.

        Args:
            session_id: The session to delete.

        Returns:
            Number of messages deleted.
        """
        ...

    def list_sessions(self) -> list[str]:
        """List all available conversation session IDs.

        Returns:
            List of session ID strings.
        """
        ...
