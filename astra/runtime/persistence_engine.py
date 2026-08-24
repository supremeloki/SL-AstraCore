from __future__ import annotations

from typing import Any

from astra.runtime.durable_graph import DurableExecutionGraph, PersistedGraph
from astra.runtime.replay_engine import ReplayEngine, ReplayEvent
from astra.runtime.compaction import SnapshotCompactor, CompactionResult


class PersistenceEngine:
    """Unified surface for runtime state persistence."""

    def __init__(self, storage_dir: str, checkpoint_dir: str, journal_path: str) -> None:
        self.graph = DurableExecutionGraph(storage_dir)
        self.replay = ReplayEngine(journal_path)
        self.compactor = SnapshotCompactor(checkpoint_dir, journal_path)

    def persist_graph(self, graph: PersistedGraph) -> str:
        return self.graph.save(graph)

    def replay_execution(self, handler) -> int:
        self.replay.load_journal()
        return self.replay.replay(handler)

    def run_compaction(self) -> CompactionResult:
        return self.compactor.compact_all()

    def get_status(self) -> dict[str, Any]:
        return {
            "snapshot_count": len(self.graph.list_snapshots()),
            "last_sequence": self.replay.get_last_sequence(),
        }