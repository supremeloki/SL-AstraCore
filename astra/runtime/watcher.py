from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Set

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent


@dataclass
class FileChange:
    """Represents a detected file change."""
    path: str
    change_type: str  # 'created', 'modified', 'deleted'
    timestamp: float = field(default_factory=time.time)


class IncrementalFileWatcher:
    """Watches a repository for file changes and triggers incremental updates.

    Uses watchdog for cross-platform file system monitoring.
    Debounces rapid changes to avoid thrashing.
    """

    def __init__(
        self,
        root_path: str,
        on_change: Callable[[list[FileChange]], None],
        file_extensions: Optional[Set[str]] = None,
        debounce_seconds: float = 0.5,
    ) -> None:
        self._root_path = str(Path(root_path).resolve())
        self._on_change = on_change
        self._file_extensions = file_extensions
        self._debounce_seconds = debounce_seconds

        self._observer: Optional[Any] = None
        self._handler: Optional[_DebouncedHandler] = None
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start watching for file changes."""
        with self._lock:
            if self._running:
                return

            self._handler = _DebouncedHandler(
                root_path=self._root_path,
                file_extensions=self._file_extensions if self._file_extensions is not None else set(),
                debounce_seconds=self._debounce_seconds,
                callback=self._process_changes,
            )

            self._observer = Observer()
            self._observer.schedule(self._handler, self._root_path, recursive=True)
            self._observer.start()
            self._running = True

    def stop(self) -> None:
        """Stop watching for file changes."""
        with self._lock:
            if not self._running:
                return

            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5.0)
                self._observer = None

            self._handler = None
            self._running = False

    def is_running(self) -> bool:
        return self._running

    def _process_changes(self, changes: list[FileChange]) -> None:
        """Callback invoked by debounced handler with accumulated changes."""
        if changes:
            self._on_change(changes)


class _DebouncedHandler(FileSystemEventHandler):
    """File system event handler with debouncing to batch rapid changes."""

    def __init__(
        self,
        root_path: str,
        file_extensions: Set[str],
        debounce_seconds: float,
        callback: Callable[[list[FileChange]], None],
    ) -> None:
        super().__init__()
        self._root_path = root_path
        self._file_extensions = file_extensions
        self._debounce_seconds = debounce_seconds
        self._callback = callback

        self._pending_changes: dict[str, FileChange] = {}
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return

        src = event.src_path or ""
        path = str(Path(str(src)).resolve())

        # Skip if not in watched extensions
        if not any(path.endswith(ext) for ext in self._file_extensions):
            return

        # Skip temp/backup files
        name = Path(path).name
        if name.startswith(".") or name.endswith("~") or name.endswith(".tmp"):
            return

        change_type = "modified"
        if event.event_type == "created":
            change_type = "created"
        elif event.event_type == "deleted":
            change_type = "deleted"

        with self._lock:
            self._pending_changes[path] = FileChange(
                path=path,
                change_type=change_type,
            )

            if self._timer:
                self._timer.cancel()

            self._timer = threading.Timer(
                self._debounce_seconds,
                self._flush_changes,
            )
            self._timer.start()

    def _flush_changes(self) -> None:
        with self._lock:
            changes = list(self._pending_changes.values())
            self._pending_changes.clear()
            self._timer = None

        if changes:
            self._callback(changes)
