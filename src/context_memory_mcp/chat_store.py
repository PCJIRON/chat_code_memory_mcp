"""ChromaDB-based chat history storage.

Manages persistent storage and retrieval of conversation turns
using ChromaDB vector embeddings for semantic search.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from mcp.server.fastmcp import FastMCP
from pydantic import Field

# Module-level singleton — instantiated once at server startup
_store: ChatStore | None = None

# Default session index path (overridable per-instance for testing)
_DEFAULT_SESSION_INDEX_PATH = "./data/session_index.json"


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
        session_index_path: str = _DEFAULT_SESSION_INDEX_PATH,
    ) -> None:
        """Initialize the ChatStore.

        ⚠️ First instantiation of SentenceTransformerEmbeddingFunction
        downloads ~80MB model (~25s). This is expected — do not interrupt.

        Args:
            collection_name: Name of the ChromaDB collection to use.
            chroma_path: Path for persistent storage. Defaults to ./data/chromadb.
            session_index_path: Path for session index JSON. Defaults to ./data/session_index.json.
        """
        self._client = chromadb.PersistentClient(path=chroma_path)
        self._ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        # Session index for O(1) list_sessions()
        self._session_index_path = session_index_path
        self._session_index: dict[str, dict] = {}
        self._load_session_index()

    def close(self) -> None:
        """Close the ChromaDB client to release SQLite file locks.

        CRITICAL on Windows: must be called before process exit.
        """
        self._client.close()

    def _load_session_index(self) -> None:
        """Load session index from disk. Rebuild from ChromaDB if missing."""
        if os.path.exists(self._session_index_path):
            with open(self._session_index_path, "r") as f:
                data = json.load(f)
                self._session_index = data.get("sessions", {})
        else:
            self._rebuild_session_index()

    def _rebuild_session_index(self) -> None:
        """Rebuild session index from ChromaDB collection."""
        result = self._collection.get(include=["metadatas"])
        self._session_index = {}
        for meta in result["metadatas"]:
            sid = meta["session_id"]
            ts = meta.get("timestamp", "")
            if sid not in self._session_index or ts > self._session_index[sid].get("last_message", ""):
                existing = self._session_index.get(sid, {"message_count": 0})
                self._session_index[sid] = {
                    "message_count": existing["message_count"] + 1,
                    "first_message": existing.get("first_message", ts),
                    "last_message": ts,
                }
        self._save_session_index()

    def _save_session_index(self) -> None:
        """Save session index to disk."""
        os.makedirs(os.path.dirname(self._session_index_path), exist_ok=True)
        with open(self._session_index_path, "w") as f:
            json.dump({
                "sessions": self._session_index,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, f, indent=2)

    def _update_session_index(self, session_id: str, timestamp: str) -> None:
        """Update session index entry after store operation."""
        if session_id not in self._session_index:
            self._session_index[session_id] = {
                "message_count": 0,
                "first_message": timestamp,
                "last_message": timestamp,
            }
        entry = self._session_index[session_id]
        entry["message_count"] += 1
        entry["last_message"] = timestamp
        self._save_session_index()

    def _remove_from_session_index(self, session_id: str) -> None:
        """Remove session from index after delete operation."""
        if session_id in self._session_index:
            del self._session_index[session_id]
            self._save_session_index()

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

        # Update session index
        self._update_session_index(session_id, now)

        return {"stored": len(messages), "session_id": session_id}

    def _build_where(
        self,
        session_id: str | None = None,
        role: str | None = None,
        doc_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Build ChromaDB where clause from optional filters.

        Returns None if no filters, single dict if one filter,
        or {'$and': [...]} if multiple filters.

        Args:
            session_id: Optional session ID filter.
            role: Optional role filter.
            doc_type: Optional document type filter ("chat" or "file_change").
        """
        conditions: list[dict[str, Any]] = []
        if session_id:
            conditions.append({"session_id": session_id})
        if role:
            conditions.append({"role": role})
        if doc_type:
            conditions.append({"type": doc_type})
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

        Raises:
            ValueError: If date_from or date_to is not valid ISO 8601 format.
        """
        # Validate date formats
        if date_from:
            try:
                datetime.fromisoformat(date_from)
            except ValueError:
                raise ValueError(
                    f"Invalid date_from format: {date_from}. Expected ISO 8601."
                )

        if date_to:
            try:
                datetime.fromisoformat(date_to)
            except ValueError:
                raise ValueError(
                    f"Invalid date_to format: {date_to}. Expected ISO 8601."
                )

        # Handle date_from > date_to — swap with warning
        if date_from and date_to and date_from > date_to:
            logging.warning(
                f"date_from ({date_from}) > date_to ({date_to}) — swapping"
            )
            date_from, date_to = date_to, date_from

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

        # Apply date filtering + type filtering in Python
        # Treat missing type as "chat" for backward compatibility
        filtered: list[dict[str, Any]] = []
        for i in range(len(docs)):
            ts = metas[i]["timestamp"]
            # Skip file_change documents — only return chat messages
            doc_type = metas[i].get("type", "chat")
            if doc_type == "file_change":
                continue
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

    def store_file_change(
        self,
        file_change: dict,
        session_id: str | None = None,
    ) -> dict:
        """Store a file change document in the same collection as chat messages.

        File changes are stored with type="file_change" metadata for filtering.

        Args:
            file_change: Dict with keys: file_path, change_type, symbols_added,
                symbols_removed, snippet (optional), timestamp (optional).
            session_id: Optional session ID for grouping.

        Returns:
            Dict with 'stored' count and 'id'.

        Raises:
            ValueError: If file_change is missing required keys.
        """
        required_keys = ("file_path", "change_type")
        for key in required_keys:
            if key not in file_change:
                raise ValueError(f"file_change missing required key: {key}")

        now = datetime.now(timezone.utc).isoformat()
        uid = "fc_" + uuid.uuid4().hex

        # Build document string: "{change_type} {file_path}: {snippet}"
        snippet = file_change.get("snippet", "")
        # Truncate snippet to 200 chars for embedding quality
        if len(snippet) > 200:
            snippet = snippet[:200] + "..."

        doc = f"{file_change['change_type']} {file_change['file_path']}: {snippet}"

        metadata = {
            "type": "file_change",
            "file_path": file_change["file_path"],
            "change_type": file_change["change_type"],
            "symbols": file_change.get("symbols_added", "")[:500],
            "timestamp": file_change.get("timestamp", now),
        }
        if session_id:
            metadata["session_id"] = session_id

        self._collection.add(
            ids=[uid],
            documents=[doc],
            metadatas=[metadata],
        )

        return {"stored": 1, "id": uid}

    def query_file_changes(
        self,
        query: str,
        top_k: int = 5,
        date_from: str | None = None,
        date_to: str | None = None,
        file_path: str | None = None,
        change_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query file change documents by semantic similarity with optional filters.

        Args:
            query: Natural language search query.
            top_k: Number of results to return.
            date_from: ISO 8601 start date.
            date_to: ISO 8601 end date.
            file_path: Filter to specific file path.
            change_type: Filter by change type (modified/created/deleted).

        Returns:
            List of result dicts with content, file_path, change_type, symbols,
            timestamp, distance, similarity.
        """
        # Build where clause
        conditions: list[dict[str, Any]] = [{"type": "file_change"}]
        if file_path:
            conditions.append({"file_path": file_path})
        if change_type:
            conditions.append({"change_type": change_type})

        if len(conditions) == 1:
            where = conditions[0]
        else:
            where = {"$and": conditions}

        # Over-fetch for date filtering
        n_results = max(top_k * 3, 50)

        result = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        docs = result["documents"][0]
        metas = result["metadatas"][0]
        dists = result["distances"][0]

        # Apply date filtering in Python
        filtered: list[dict[str, Any]] = []
        for i in range(len(docs)):
            ts = metas[i].get("timestamp", "")
            if date_from and ts < date_from:
                continue
            if date_to and ts > date_to:
                continue
            distance = dists[i]
            filtered.append({
                "content": docs[i],
                "file_path": metas[i].get("file_path", ""),
                "change_type": metas[i].get("change_type", ""),
                "symbols": metas[i].get("symbols", ""),
                "timestamp": ts,
                "distance": round(distance, 4),
                "similarity": round(1 - distance, 4),
            })

        return filtered[:top_k]

    def list_sessions(self) -> list[str]:
        """List all available conversation session IDs from index (O(1)).

        Returns:
            Sorted list of distinct session IDs.
        """
        return sorted(self._session_index.keys())

    def prune_sessions(
        self,
        before_date: str | None = None,
        max_sessions: int | None = None,
    ) -> dict:
        """Remove old sessions to control collection size.

        Args:
            before_date: Delete sessions with last_message before this ISO 8601 date.
            max_sessions: Keep only N most recent sessions.

        Returns:
            Dict with 'pruned' count and 'remaining' count.
        """
        # Get all session metadata (ID + last message timestamp)
        result = self._collection.get(include=["metadatas"])
        session_map: dict[str, str] = {}
        for meta in result["metadatas"]:
            sid = meta["session_id"]
            ts = meta.get("timestamp", "")
            if sid not in session_map or ts > session_map[sid]:
                session_map[sid] = ts

        if not session_map:
            return {"pruned": 0, "remaining": 0}

        to_delete = set()

        # Apply date filter
        if before_date:
            for sid, last_msg in session_map.items():
                if last_msg < before_date:
                    to_delete.add(sid)

        # Apply max_sessions cap (on remaining after date filter)
        if max_sessions is not None:
            remaining = [
                (sid, ts) for sid, ts in session_map.items() if sid not in to_delete
            ]
            remaining.sort(key=lambda x: x[1], reverse=True)
            for sid, _ in remaining[max_sessions:]:
                to_delete.add(sid)

        # Delete pruned sessions
        pruned = 0
        for sess_id in to_delete:
            self.delete_session(sess_id)
            pruned += 1

        # Update session index after pruning
        self._save_session_index()

        return {"pruned": pruned, "remaining": len(session_map) - pruned}

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
        # Remove from session index
        self._remove_from_session_index(session_id)
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
        conversation_id: Annotated[
            str | None,
            Field(description="Alias for session_id"),
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
        # Handle conversation_id alias
        if conversation_id and not session_id:
            session_id = conversation_id
        elif conversation_id and session_id:
            logging.warning(
                "Both session_id and conversation_id provided — using conversation_id"
            )
            session_id = conversation_id

        # Validate: reject empty strings
        if session_id == "":
            raise ValueError("session_id cannot be empty")
        if conversation_id == "":
            raise ValueError("conversation_id cannot be empty")

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
