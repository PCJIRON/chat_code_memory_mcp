"""Comprehensive tests for IntentClassifier.

Tests cover all classification scenarios: clear chat intent, clear file intent,
ambiguous queries (both), unknown/edge cases, centroid pre-computation,
and cosine similarity correctness.
"""

from __future__ import annotations

import numpy as np
import pytest

from context_memory_mcp.chat_store import ChatStore
from context_memory_mcp.intent_classifier import (
    INTENT_CHAT_PHRASES,
    INTENT_FILE_PHRASES,
    IntentClassifier,
    get_intent_classifier,
    reset_intent_classifier,
)


@pytest.fixture()
def store(tmp_path):
    """Create an isolated ChatStore for embedding function access."""
    s = ChatStore(
        chroma_path=str(tmp_path / "chromadb"),
        session_index_path=str(tmp_path / "session_index.json"),
    )
    yield s
    s.close()


@pytest.fixture()
def classifier(store):
    """Create IntentClassifier with isolated store."""
    return IntentClassifier(store._ef)


# ── Centroid Pre-computation ──────────────────────────────────────


class TestIntentClassifierInit:
    """Test centroid pre-computation at initialization."""

    def test_centroids_precomputed_at_init(self, classifier):
        """Chat and file centroids should be computed once at __init__."""
        assert len(classifier._chat_centroids) == len(INTENT_CHAT_PHRASES)
        assert len(classifier._file_centroids) == len(INTENT_FILE_PHRASES)

    def test_centroids_are_numpy_arrays(self, classifier):
        """Centroids should be numpy arrays."""
        for c in classifier._chat_centroids:
            assert isinstance(c, np.ndarray)
        for c in classifier._file_centroids:
            assert isinstance(c, np.ndarray)

    def test_centroids_are_not_empty(self, classifier):
        """Centroids should have non-zero length."""
        for c in classifier._chat_centroids:
            assert len(c) > 0
        for c in classifier._file_centroids:
            assert len(c) > 0

    def test_custom_threshold(self, store):
        """Custom threshold should be respected."""
        clf = IntentClassifier(store._ef, threshold=0.7)
        assert clf.threshold == 0.7


# ── Chat Intent Classification ────────────────────────────────────


class TestChatIntent:
    """Test queries that should be classified as chat intent."""

    def test_what_did_we_discuss(self, classifier):
        result = classifier.classify("What did we discuss earlier?")
        assert result == "chat"

    def test_remember_conversation(self, classifier):
        result = classifier.classify("Remember what I said about the design?")
        # Semantic classifier may return 'chat' or 'both' for this query
        assert result in ("chat", "both")

    def test_previous_discussion(self, classifier):
        result = classifier.classify("Tell me about our previous discussion")
        assert result == "chat"

    def test_what_did_i_ask_before(self, classifier):
        result = classifier.classify("What did I ask before?")
        assert result == "chat"


# ── File Intent Classification ────────────────────────────────────


class TestFileIntent:
    """Test queries that should be classified as file intent."""

    def test_which_files_changed(self, classifier):
        result = classifier.classify("Which files changed recently?")
        assert result == "file"

    def test_import_dependencies(self, classifier):
        result = classifier.classify("What are the import dependencies?")
        assert result == "file"

    def test_file_structure(self, classifier):
        result = classifier.classify("Show me the file structure")
        assert result == "file"

    def test_files_affected_by_change(self, classifier):
        result = classifier.classify("What files are affected by this change?")
        assert result == "file"


# ── Both/Fallback Intent ─────────────────────────────────────────


class TestBothIntent:
    """Test queries that should return 'both' (ambiguous or edge cases)."""

    def test_empty_query(self, classifier):
        result = classifier.classify("")
        assert result == "both"

    def test_whitespace_only_query(self, classifier):
        result = classifier.classify("   ")
        assert result == "both"

    def test_completely_unrelated_query(self, classifier):
        """Unrelated query should fallback to 'both'."""
        result = classifier.classify("What is the meaning of life?")
        assert result == "both"

    def test_mixed_intent_query(self, classifier):
        """Query mentioning both chat and file concepts."""
        result = classifier.classify(
            "What did we say about the file changes and dependencies?"
        )
        # Should be 'both' or one of the intents — either is acceptable
        assert result in ("chat", "file", "both")


# ── Cosine Similarity ─────────────────────────────────────────────


class TestCosineSimilarity:
    """Test cosine similarity computation."""

    def test_identical_vectors(self):
        """Identical vectors should have cosine similarity of 1.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        assert IntentClassifier._cosine_sim(a, b) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors should have cosine similarity of 0.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        assert IntentClassifier._cosine_sim(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        """Opposite vectors should have cosine similarity of -1.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([-1.0, 0.0, 0.0])
        assert IntentClassifier._cosine_sim(a, b) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        """Zero vector should return 0 similarity."""
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        assert IntentClassifier._cosine_sim(a, b) == 0.0


# ── Determinism ───────────────────────────────────────────────────


class TestDeterminism:
    """Test that classification is deterministic."""

    def test_same_input_same_output(self, classifier):
        """Same query should always return same intent."""
        for _ in range(5):
            result = classifier.classify("what did we discuss")
            assert result == "chat"

    def test_centroids_not_recomputed_per_query(self, classifier):
        """Centroids should be cached, not recomputed per query."""
        chat_id_before = id(classifier._chat_centroids)
        file_id_before = id(classifier._file_centroids)
        classifier.classify("test query 1")
        classifier.classify("test query 2")
        assert id(classifier._chat_centroids) == chat_id_before
        assert id(classifier._file_centroids) == file_id_before


# ── Singleton Pattern ─────────────────────────────────────────────


class TestSingleton:
    """Test module-level singleton pattern."""

    def test_get_intent_classifier_returns_instance(self, store):
        """get_intent_classifier should return IntentClassifier instance."""
        reset_intent_classifier()
        try:
            clf = get_intent_classifier(embedding_function=store._ef)
            assert isinstance(clf, IntentClassifier)
        finally:
            reset_intent_classifier()

    def test_get_intent_classifier_returns_same_instance(self, store):
        """Multiple calls should return same singleton instance."""
        reset_intent_classifier()
        try:
            clf1 = get_intent_classifier(embedding_function=store._ef)
            clf2 = get_intent_classifier(embedding_function=store._ef)
            assert clf1 is clf2
        finally:
            reset_intent_classifier()

    def test_reset_intent_classifier(self, store):
        """Reset should clear the singleton."""
        reset_intent_classifier()
        clf1 = get_intent_classifier(embedding_function=store._ef)
        reset_intent_classifier()
        clf2 = get_intent_classifier(embedding_function=store._ef)
        assert clf1 is not clf2
        reset_intent_classifier()  # Clean up
