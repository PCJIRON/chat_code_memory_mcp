"""ChromaDB-based chat history storage.

Manages persistent storage and retrieval of conversation turns
using ChromaDB vector embeddings for semantic search.
"""

from __future__ import annotations

from typing import Any


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
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serialize the message to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatMessage:
        """Deserialize a message from a dictionary.

        Args:
            data: Dictionary with message fields.

        Returns:
            A new ChatMessage instance.
        """
        ...


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
        ...

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
