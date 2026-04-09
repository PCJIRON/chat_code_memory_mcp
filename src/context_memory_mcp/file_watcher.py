"""File watcher for automatic file change tracking.

Uses watchdog Observer + FileSystemEventHandler to monitor
directories and auto-update the FileGraph on file changes.
Includes 0.5s debounce for OneDrive delayed/duplicate events.
"""

from __future__ import annotations

import os
import time
import logging

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class AutoTrackHandler(FileSystemEventHandler):
    """FileSystemEventHandler that debounces events and updates FileGraph.

    Attributes:
        graph: FileGraph instance to update.
        root_dir: Root directory being watched.
        ignore_dirs: Set of directory names to ignore.
    """

    def __init__(
        self,
        graph,
        root_dir: str,
        ignore_dirs: list[str],
    ) -> None:
        """Initialize AutoTrackHandler.

        Args:
            graph: FileGraph instance to update on file changes.
            root_dir: Root directory being watched.
            ignore_dirs: Directory names to ignore (e.g. .git, __pycache__).
        """
        self.graph = graph
        self.root_dir = os.path.abspath(root_dir)
        self.ignore_dirs = set(ignore_dirs)
        self._last_event = 0.0
        self._debounce = 0.5  # seconds (OneDrive handling)

    def _should_ignore(self, path: str) -> bool:
        """Check if path should be ignored based on directory names.

        Args:
            path: File or directory path to check.

        Returns:
            True if path contains an ignored directory component.
        """
        parts = os.path.normpath(path).split(os.sep)
        return bool(set(parts) & self.ignore_dirs)

    def _debounce_event(self) -> bool:
        """Check and apply debounce. Returns True if event should be skipped.

        Returns:
            True if event is within debounce window (should skip).
        """
        now = time.monotonic()
        if now - self._last_event < self._debounce:
            return True
        self._last_event = now
        return False

    def on_modified(self, event) -> None:  # noqa: ANN001
        """Handle file modification event.

        Args:
            event: FileSystemEvent from watchdog.
        """
        if event.is_directory or self._should_ignore(event.src_path) or self._debounce_event():
            return
        try:
            self.graph.update_graph(self.root_dir)
        except Exception as e:
            logging.error(f"Auto-track failed: {e}")

    def on_created(self, event) -> None:  # noqa: ANN001
        """Handle file creation event.

        Args:
            event: FileSystemEvent from watchdog.
        """
        self.on_modified(event)


class FileWatcher:
    """Manages watchdog Observer lifecycle.

    Schedules observers for watch directories and handles clean shutdown.
    Observer runs its own OS thread — no asyncio.create_task() needed.

    Attributes:
        watch_dirs: Directories to monitor.
        ignore_dirs: Directory names to skip.
        graph: FileGraph to update on changes.
    """

    def __init__(
        self,
        watch_dirs: list[str],
        ignore_dirs: list[str],
        graph,
    ) -> None:
        """Initialize FileWatcher.

        Args:
            watch_dirs: List of directories to monitor.
            ignore_dirs: Directory names to ignore within watched dirs.
            graph: FileGraph instance to update on changes.
        """
        self.watch_dirs = watch_dirs
        self.ignore_dirs = ignore_dirs
        self.graph = graph
        self._observer = Observer()
        self._running = False

    def start(self) -> None:
        """Start watching directories.

        Creates handler, schedules existing directories, starts observer.
        Non-existent directories are skipped with a warning.
        """
        root_dir = self.watch_dirs[0] if self.watch_dirs else "."
        handler = AutoTrackHandler(self.graph, root_dir, self.ignore_dirs)

        for d in self.watch_dirs:
            if os.path.isdir(d):
                self._observer.schedule(handler, path=d, recursive=True)
            else:
                logging.warning(f"Watch directory does not exist, skipping: {d}")

        self._observer.daemon = True
        self._observer.start()
        self._running = True

    def stop(self) -> None:
        """Stop watching and join observer thread.

        Clean shutdown: calls stop() then join(timeout=5).
        """
        if self._running:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._running = False
