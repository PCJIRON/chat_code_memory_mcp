"""Local embedding wrapper using sentence-transformers.

Provides text embedding capabilities for semantic search
and similarity computations, running entirely locally.
"""

from __future__ import annotations

import numpy as np


class EmbeddingModel:
    """Local embedding model using sentence-transformers.

    Encodes text into dense vector representations for semantic
    similarity search and clustering.

    Attributes:
        model_name: Name of the sentence-transformers model.
        dimension: Dimensionality of the embedding vectors.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Initialize the EmbeddingModel.

        Args:
            model_name: Name of the sentence-transformers model to use.
        """
        ...

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode a list of texts into embeddings.

        Args:
            texts: List of text strings to encode.

        Returns:
            Numpy array of shape (n_texts, dimension) with embeddings.
        """
        ...

    def encode_single(self, text: str) -> list[float]:
        """Encode a single text into an embedding.

        Args:
            text: Text string to encode.

        Returns:
            List of floats representing the embedding vector.
        """
        ...

    def similarity(self, text1: str, text2: str) -> float:
        """Compute cosine similarity between two texts.

        Args:
            text1: First text string.
            text2: Second text string.

        Returns:
            Cosine similarity score between -1 and 1.
        """
        ...

    @property
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors.

        Returns:
            Embedding dimension as an integer.
        """
        ...
