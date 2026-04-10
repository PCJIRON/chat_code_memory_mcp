"""Semantic intent classification using sentence-transformers centroids.

Classifies user queries into intent categories (chat, file, both, unknown)
by comparing embeddings against pre-computed intent centroids using
cosine similarity. Zero new dependencies — uses existing model.
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np

# Intent centroid phrases — these define the semantic "center" of each intent
INTENT_CHAT_PHRASES = [
    "what did we discuss previously",
    "remember what was said in our conversation",
    "what did I ask before",
    "tell me about our previous discussion",
]

INTENT_FILE_PHRASES = [
    "which files changed recently",
    "what are the import dependencies",
    "show me the file structure",
    "what files are affected by this change",
]

# Cosine similarity threshold — scores above this indicate intent match
_DEFAULT_THRESHOLD = 0.5


class IntentClassifier:
    """Semantic intent classification using pre-computed intent centroids.

    Embeds canonical intent phrases at startup, caches the embeddings,
    then classifies queries by comparing against these centroids using
    cosine similarity.

    Attributes:
        threshold: Cosine similarity threshold for intent matching.
    """

    def __init__(
        self,
        embedding_function,
        threshold: float = _DEFAULT_THRESHOLD,
    ) -> None:
        """Initialize IntentClassifier with pre-computed centroids.

        Args:
            embedding_function: SentenceTransformerEmbeddingFunction instance.
            threshold: Cosine similarity threshold for intent matching.
        """
        self._ef = embedding_function
        self.threshold = threshold

        # Pre-compute centroids at startup (one-time cost)
        self._chat_centroids = self._embed_batch(INTENT_CHAT_PHRASES)
        self._file_centroids = self._embed_batch(INTENT_FILE_PHRASES)

        logging.info(
            "IntentClassifier initialized with %d chat centroids, "
            "%d file centroids (threshold=%.2f)",
            len(self._chat_centroids),
            len(self._file_centroids),
            threshold,
        )

    def _embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Embed a list of texts and return numpy arrays.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of numpy embedding arrays.
        """
        embeddings = self._ef(texts)
        return [np.array(emb) for emb in embeddings]

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            a: First vector.
            b: Second vector.

        Returns:
            Cosine similarity score in [-1, 1].
        """
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def classify(
        self, query: str
    ) -> Literal["chat", "file", "both", "unknown"]:
        """Classify a query into an intent category.

        Args:
            query: User query string to classify.

        Returns:
            One of "chat", "file", "both", or "unknown".
        """
        if not query or not query.strip():
            return "both"  # Safe fallback for empty queries

        q_emb = np.array(self._ef([query])[0])

        # Compute max similarity to each intent centroid
        chat_score = max(
            self._cosine_sim(q_emb, c) for c in self._chat_centroids
        )
        file_score = max(
            self._cosine_sim(q_emb, c) for c in self._file_centroids
        )

        is_chat = chat_score > self.threshold
        is_file = file_score > self.threshold

        if is_chat and is_file:
            return "both"
        elif is_chat:
            return "chat"
        elif is_file:
            return "file"
        else:
            return "both"  # Safe fallback — retrieve from both sources


# Module-level singleton pattern
_intent_classifier: IntentClassifier | None = None


def get_intent_classifier(
    embedding_function=None,
    threshold: float = _DEFAULT_THRESHOLD,
) -> IntentClassifier:
    """Get or create the module-level IntentClassifier singleton.

    Args:
        embedding_function: SentenceTransformerEmbeddingFunction.
            Auto-created from ChatStore if not provided.
        threshold: Cosine similarity threshold.

    Returns:
        IntentClassifier instance.
    """
    global _intent_classifier
    if _intent_classifier is None:
        if embedding_function is None:
            # Import here to avoid circular imports
            from context_memory_mcp.chat_store import get_store

            store = get_store()
            embedding_function = store._ef
        _intent_classifier = IntentClassifier(
            embedding_function, threshold
        )
    return _intent_classifier


def reset_intent_classifier() -> None:
    """Reset the IntentClassifier singleton (useful for testing)."""
    global _intent_classifier
    _intent_classifier = None
