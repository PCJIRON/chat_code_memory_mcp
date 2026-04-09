"""Tests for FileWatcher with mocked Observer."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from context_memory_mcp.file_watcher import AutoTrackHandler, FileWatcher


@pytest.fixture
def mock_graph():
    """Mock FileGraph for testing."""
    graph = MagicMock()
    return graph


class TestFileWatcher:
    """Tests for FileWatcher class."""

    @patch("context_memory_mcp.file_watcher.Observer")
    def test_file_watcher_starts_and_stops(self, mock_observer_class, mock_graph):
        """start() and stop() should call observer methods."""
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer

        watcher = FileWatcher(["./src"], [".git"], mock_graph)
        watcher.start()
        mock_observer.start.assert_called_once()
        mock_observer_class.assert_called_once()

        watcher.stop()
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()
        assert watcher._running is False

    @patch("context_memory_mcp.file_watcher.Observer")
    def test_file_watcher_skips_nonexistent_dirs(self, mock_observer_class, mock_graph):
        """Non-existent watch dirs should be skipped, no exception."""
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer

        watcher = FileWatcher(["./nonexistent_dir_xyz"], [".git"], mock_graph)
        watcher.start()  # Should not raise
        # schedule() should not be called for nonexistent dir
        assert mock_observer.schedule.call_count == 0
        watcher.stop()

    @patch("context_memory_mcp.file_watcher.Observer")
    def test_file_watcher_observer_is_daemon(self, mock_observer_class, mock_graph):
        """Observer should be set as daemon thread."""
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer

        watcher = FileWatcher(["./src"], [".git"], mock_graph)
        watcher.start()
        # Check that daemon was set on the observer
        assert mock_observer.daemon is True
        watcher.stop()


class TestAutoTrackHandler:
    """Tests for AutoTrackHandler class."""

    def test_handler_ignores_directories(self, mock_graph):
        """on_modified with is_directory=True should be no-op."""
        handler = AutoTrackHandler(mock_graph, "./src", [".git"])
        event = MagicMock()
        event.is_directory = True
        event.src_path = "./src/test.py"
        handler.on_modified(event)
        mock_graph.update_graph.assert_not_called()

    def test_handler_ignores_skip_dirs(self, mock_graph):
        """_should_ignore should return True for .git and __pycache__ paths."""
        handler = AutoTrackHandler(mock_graph, "./src", [".git", "__pycache__"])
        assert handler._should_ignore("./src/.git/config") is True
        assert handler._should_ignore("./src/__pycache__/module.pyc") is True
        assert handler._should_ignore("./src/module.py") is False

    def test_handler_debounces_rapid_events(self, mock_graph):
        """Two events within 0.5s should only trigger first graph update."""
        handler = AutoTrackHandler(mock_graph, "./src", [".git"])
        handler._debounce = 0.5

        # First event — should process
        event1 = MagicMock()
        event1.is_directory = False
        event1.src_path = "./src/module.py"
        handler.on_modified(event1)
        assert mock_graph.update_graph.call_count == 1

        # Second event immediately — should be debounced
        event2 = MagicMock()
        event2.is_directory = False
        event2.src_path = "./src/module2.py"
        handler.on_modified(event2)
        # Still 1 call — second was debounced
        assert mock_graph.update_graph.call_count == 1

    def test_handler_processes_after_debounce_window(self, mock_graph):
        """Events after 0.5s debounce window should be processed."""
        handler = AutoTrackHandler(mock_graph, "./src", [".git"])
        handler._debounce = 0.1  # Use shorter for test speed

        event1 = MagicMock()
        event1.is_directory = False
        event1.src_path = "./src/module.py"
        handler.on_modified(event1)
        assert mock_graph.update_graph.call_count == 1

        # Wait for debounce window
        time.sleep(0.15)

        event2 = MagicMock()
        event2.is_directory = False
        event2.src_path = "./src/module2.py"
        handler.on_modified(event2)
        assert mock_graph.update_graph.call_count == 2

    def test_handler_on_created_calls_on_modified(self, mock_graph):
        """on_created should delegate to on_modified."""
        handler = AutoTrackHandler(mock_graph, "./src", [".git"])
        handler._debounce = 0.0  # No debounce for this test

        event = MagicMock()
        event.is_directory = False
        event.src_path = "./src/new_file.py"
        handler.on_created(event)
        mock_graph.update_graph.assert_called_once()

    def test_handler_exception_in_update_graph_is_logged(self, mock_graph):
        """Exception in graph.update_graph should be logged, not raised."""
        mock_graph.update_graph.side_effect = RuntimeError("Graph error")
        handler = AutoTrackHandler(mock_graph, "./src", [".git"])
        handler._debounce = 0.0

        event = MagicMock()
        event.is_directory = False
        event.src_path = "./src/module.py"
        handler.on_modified(event)  # Should not raise
