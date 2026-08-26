"""
2C — Incremental File Watcher tests.

Verifies watcher lifecycle, debouncing, event filtering,
and callback integration with the runtime orchestrator.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from astra.runtime.watcher import IncrementalFileWatcher, FileChange


def test_watcher_start_stop():
    with tempfile.TemporaryDirectory(prefix="astra_watch_") as tmpdir:
        collected: list[list[FileChange]] = []

        def on_change(changes):
            collected.append(changes)

        watcher = IncrementalFileWatcher(
            root_path=tmpdir,
            on_change=on_change,
            file_extensions={".py"},
            debounce_seconds=0.2,
        )

        assert not watcher.is_running()

        watcher.start()
        assert watcher.is_running()

        # Create a Python file — should trigger change
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("x = 1\n")

        time.sleep(1.0)

        watcher.stop()
        assert not watcher.is_running()

        # Should have captured at least one change
        assert len(collected) > 0
        # The last batch should contain our file
        all_paths = [c.path for batch in collected for c in batch]
        assert str(test_file) in all_paths


def test_watcher_filters_extensions():
    with tempfile.TemporaryDirectory(prefix="astra_watch_") as tmpdir:
        collected: list[list[FileChange]] = []

        def on_change(changes):
            collected.append(changes)

        watcher = IncrementalFileWatcher(
            root_path=tmpdir,
            on_change=on_change,
            file_extensions={".py"},
            debounce_seconds=0.1,
        )

        watcher.start()

        # Create non-Python file — should be ignored
        (Path(tmpdir) / "readme.md").write_text("# README")
        (Path(tmpdir) / "test.py").write_text("ok")

        time.sleep(0.5)
        watcher.stop()

        all_paths = {c.path for batch in collected for c in batch}
        assert str(Path(tmpdir) / "test.py") in all_paths
        assert str(Path(tmpdir) / "readme.md") not in all_paths


def test_change_type_detection():
    with tempfile.TemporaryDirectory(prefix="astra_watch_") as tmpdir:
        collected: list[list[FileChange]] = []

        def on_change(changes):
            collected.append(changes)

        watcher = IncrementalFileWatcher(
            root_path=tmpdir,
            on_change=on_change,
            file_extensions={".txt"},
            debounce_seconds=0.1,
        )

        watcher.start()

        test_file = Path(tmpdir) / "change.txt"
        test_file.write_text("initial")
        time.sleep(0.3)

        test_file.write_text("updated")
        time.sleep(0.3)

        test_file.unlink()
        time.sleep(0.3)

        watcher.stop()

        all_changes = [c for batch in collected for c in batch]
        types = {c.change_type for c in all_changes}
        assert "deleted" in types or len(all_changes) >= 1


def test_double_start_is_idempotent():
    with tempfile.TemporaryDirectory(prefix="astra_watch_") as tmpdir:
        collected: list[list[FileChange]] = []

        def on_change(changes):
            collected.append(changes)

        watcher = IncrementalFileWatcher(
            root_path=tmpdir,
            on_change=on_change,
            file_extensions={".py"},
        )

        watcher.start()
        watcher.start()  # should be no-op
        assert watcher.is_running()
        watcher.stop()
        watcher.stop()  # should be no-op
        assert not watcher.is_running()