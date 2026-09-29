from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional
import time


@dataclass
class PersistedGraph:
    """Serializable snapshot of graph state."""
    nodes: dict[str, dict] = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1


class DurableExecutionGraph:
    """Persist execution graph state to backend storage with snapshots."""

    def __init__(self, storage_dir: str) -> None:
        self._storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        self._base_path = os.path.join(storage_dir, "execution_graph.json")

    def save(self, graph: PersistedGraph) -> str:
        """Save graph state atomically."""
        tmp_path = self._base_path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump({
                "nodes": graph.nodes,
                "edges": graph.edges,
                "metadata": {**graph.metadata, "saved_at": time.time()},
                "version": graph.version,
            }, f, indent=2)
        os.replace(tmp_path, self._base_path)
        return self._base_path

    def load(self) -> Optional[PersistedGraph]:
        """Load persisted graph state."""
        if not os.path.exists(self._base_path):
            return None
        with open(self._base_path) as f:
            data = json.load(f)
        return PersistedGraph(
            nodes=data.get("nodes", {}),
            edges=data.get("edges", []),
            metadata=data.get("metadata", {}),
            version=data.get("version", 1),
        )

    def snapshot(self, name: str) -> str:
        """Create a named snapshot."""
        graph = self.load()
        if graph is None:
            return ""
        snapshot_path = os.path.join(self._storage_dir, f"snapshot_{name}.json")
        with open(snapshot_path, "w") as f:
            json.dump({
                "nodes": graph.nodes,
                "edges": graph.edges,
                "metadata": graph.metadata,
                "version": graph.version,
                "snapshot_name": name,
                "snapshot_time": time.time(),
            }, f, indent=2)
        return snapshot_path

    def list_snapshots(self) -> list[str]:
        """List available snapshot names."""
        snapshots = []
        for f in os.listdir(self._storage_dir):
            if f.startswith("snapshot_") and f.endswith(".json"):
                snapshots.append(f[len("snapshot_"):-len(".json")])
        return sorted(snapshots)

    def delete_snapshot(self, name: str) -> bool:
        """Delete a named snapshot."""
        snapshot_path = os.path.join(self._storage_dir, f"snapshot_{name}.json")
        if os.path.exists(snapshot_path):
            os.remove(snapshot_path)
            return True
        return False
