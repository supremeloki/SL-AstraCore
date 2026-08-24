from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CompactionResult:
    """Result of a compaction operation."""
    journal_entries_before: int
    journal_entries_after: int
    checkpoints_pruned: int
    space_reclaimed_bytes: int
    duration_seconds: float


class SnapshotCompactor:
    """Compact journal and prune checkpoints to manage storage growth."""

    def __init__(self, checkpoint_dir: str, journal_path: str) -> None:
        self._checkpoint_dir = checkpoint_dir
        self._journal_path = journal_path

    def compact_journal(self, keep_last_n: int = 100) -> CompactionResult:
        """Compact journal by keeping only the last N entries."""
        start = time.time()
        entries_before = 0
        entries_after = 0
        space_before = 0
        space_after = 0

        if os.path.exists(self._journal_path):
            with open(self._journal_path) as f:
                lines = f.readlines()
            entries_before = len(lines)
            space_before = sum(len(l) for l in lines)

            # Keep last N entries
            keep_lines = lines[-keep_last_n:] if len(lines) > keep_last_n else lines

            tmp_path = self._journal_path + ".tmp"
            with open(tmp_path, "w") as f:
                f.writelines(keep_lines)
            os.replace(tmp_path, self._journal_path)

            entries_after = len(keep_lines)
            space_after = sum(len(l) for l in keep_lines)

        return CompactionResult(
            journal_entries_before=entries_before,
            journal_entries_after=entries_after,
            checkpoints_pruned=0,
            space_reclaimed_bytes=space_before - space_after,
            duration_seconds=time.time() - start,
        )

    def prune_checkpoints(self, keep_last_n: int = 5) -> int:
        """Prune old checkpoints, keep last N."""
        if not os.path.exists(self._checkpoint_dir):
            return 0

        files = sorted(
            [f for f in os.listdir(self._checkpoint_dir) if f.endswith(".json")],
            key=lambda f: os.path.getmtime(os.path.join(self._checkpoint_dir, f))
        )

        if len(files) <= keep_last_n:
            return 0

        to_remove = files[:-keep_last_n]
        for f in to_remove:
            os.remove(os.path.join(self._checkpoint_dir, f))
        return len(to_remove)

    def compact_all(self, keep_journal: int = 100, keep_checkpoints: int = 5) -> CompactionResult:
        """Run full compaction: journal + checkpoints."""
        result = self.compact_journal(keep_journal)
        result.checkpoints_pruned = self.prune_checkpoints(keep_checkpoints)
        return result