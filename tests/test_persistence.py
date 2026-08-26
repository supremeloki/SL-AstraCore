"""3G — Persistence Layer full test suite.

Verifies:
  - DurableExecutionGraph (save, load, snapshot, list, delete, atomicity)
  - ReplayEngine (load, replay, filter, sequence tracking, export)
  - SnapshotCompactor (journal compaction, checkpoint pruning, full compact)
  - PersistenceEngine (lifecycle, graph persist, replay, compaction, status)
"""

from __future__ import annotations

import os
import json
import tempfile

from astra.runtime.durable_graph import DurableExecutionGraph, PersistedGraph
from astra.runtime.replay_engine import ReplayEngine, ReplayEvent
from astra.runtime.compaction import SnapshotCompactor
from astra.runtime.persistence_engine import PersistenceEngine


# ── Durable Graph ──────────────────────────────────────────────────

class TestDurableExecutionGraph:
    def test_save_and_load_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            deg = DurableExecutionGraph(tmp)
            deg.save(PersistedGraph())
            loaded = deg.load()
            assert loaded is not None
            assert loaded.nodes == {}
            assert loaded.edges == []

    def test_save_and_load_with_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            deg = DurableExecutionGraph(tmp)
            g = PersistedGraph(
                nodes={"n1": {"type": "file", "path": "/a.py"}},
                edges=[{"source": "n1", "target": "n2", "type": "import"}],
                metadata={"version": "1.0"},
            )
            deg.save(g)
            loaded = deg.load()
            assert loaded.nodes["n1"]["path"] == "/a.py"
            assert loaded.edges[0]["type"] == "import"
            assert loaded.metadata["version"] == "1.0"

    def test_save_is_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            deg = DurableExecutionGraph(tmp)
            deg.save(PersistedGraph(nodes={"a": {}}))
            # Simulate partial write by truncating tmp file
            tmp_path = deg._base_path + ".tmp"
            with open(tmp_path, "w") as f:
                f.write("{invalid json")  # Incomplete write
            # Main file should still be valid
            loaded = deg.load()
            assert loaded is not None
            assert "a" in loaded.nodes

    def test_snapshot_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            deg = DurableExecutionGraph(tmp)
            deg.save(PersistedGraph(nodes={"x": {}}))
            path = deg.snapshot("v1")
            assert os.path.exists(path)
            snapshots = deg.list_snapshots()
            assert "v1" in snapshots
            assert deg.delete_snapshot("v1")
            assert "v1" not in deg.list_snapshots()

    def test_multiple_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            deg = DurableExecutionGraph(tmp)
            deg.save(PersistedGraph())
            deg.snapshot("a")
            deg.snapshot("b")
            deg.snapshot("c")
            assert len(deg.list_snapshots()) == 3

    def test_delete_nonexistent_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            deg = DurableExecutionGraph(tmp)
            assert not deg.delete_snapshot("nonexistent")

    def test_load_empty_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            deg = DurableExecutionGraph(tmp)
            loaded = deg.load()
            assert loaded is None

    def test_metadata_timestamp_on_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            deg = DurableExecutionGraph(tmp)
            deg.save(PersistedGraph())
            loaded = deg.load()
            assert "saved_at" in loaded.metadata

    def test_version_propagation(self):
        with tempfile.TemporaryDirectory() as tmp:
            deg = DurableExecutionGraph(tmp)
            deg.save(PersistedGraph(version=3))
            loaded = deg.load()
            assert loaded.version == 3


# ── Replay Engine ──────────────────────────────────────────────────

class TestReplayEngine:
    def test_load_empty_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "journal.jsonl")
            re = ReplayEngine(path)
            events = re.load_journal()
            assert events == []

    def test_load_journal_events(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"event_type": "a", "sequence": 1}) + "\n")
            f.write(json.dumps({"event_type": "b", "sequence": 2}) + "\n")
            path = f.name
        try:
            re = ReplayEngine(path)
            events = re.load_journal()
            assert len(events) == 2
            assert events[0].event_type == "a"
            assert events[1].event_type == "b"
        finally:
            os.remove(path)

    def test_replay_handler(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"event_type": "scan", "sequence": 1}) + "\n")
            f.write(json.dumps({"event_type": "parse", "sequence": 2}) + "\n")
            path = f.name
        try:
            re = ReplayEngine(path)
            re.load_journal()
            replayed_types = []
            def handler(event: ReplayEvent):
                replayed_types.append(event.event_type)
            count = re.replay(handler)
            assert count == 2
            assert replayed_types == ["scan", "parse"]
        finally:
            os.remove(path)

    def test_replay_from_sequence(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"event_type": "a", "sequence": 1}) + "\n")
            f.write(json.dumps({"event_type": "b", "sequence": 2}) + "\n")
            f.write(json.dumps({"event_type": "c", "sequence": 3}) + "\n")
            path = f.name
        try:
            re = ReplayEngine(path)
            re.load_journal()
            replayed = []
            count = re.replay_from_sequence(2, lambda e: replayed.append(e.event_type))
            assert count == 2
            assert replayed == ["b", "c"]
        finally:
            os.remove(path)

    def test_get_last_sequence(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"event_type": "x", "sequence": 5}) + "\n")
            path = f.name
        try:
            re = ReplayEngine(path)
            re.load_journal()
            assert re.get_last_sequence() == 5
        finally:
            os.remove(path)

    def test_filter_events(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"event_type": "scan", "sequence": 1}) + "\n")
            f.write(json.dumps({"event_type": "parse", "sequence": 2}) + "\n")
            f.write(json.dumps({"event_type": "scan", "sequence": 3}) + "\n")
            path = f.name
        try:
            re = ReplayEngine(path)
            re.load_journal()
            scans = re.filter_events(["scan"])
            assert len(scans) == 2
            parses = re.filter_events(["parse"])
            assert len(parses) == 1
        finally:
            os.remove(path)

    def test_export_replay(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"event_type": "t", "sequence": 1}) + "\n")
            path = f.name
        try:
            re = ReplayEngine(path)
            re.load_journal()
            export_path = path + ".replay.json"
            re.export_replay(export_path)
            assert os.path.exists(export_path)
            with open(export_path) as f:
                data = json.load(f)
            assert len(data) == 1
        finally:
            os.remove(path)
            if os.path.exists(path + ".replay.json"):
                os.remove(path + ".replay.json")


# ── Snapshot Compactor ─────────────────────────────────────────────

class TestSnapshotCompactor:
    def test_compact_journal_keeps_last_n(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = os.path.join(tmp, "journal.jsonl")
            with open(journal, "w") as f:
                for i in range(50):
                    f.write(json.dumps({"event_type": "t", "sequence": i}) + "\n")

            comp = SnapshotCompactor(tmp, journal)
            result = comp.compact_journal(keep_last_n=5)

            with open(journal) as f:
                lines = f.readlines()
            assert len(lines) == 5
            assert result.journal_entries_before == 50
            assert result.journal_entries_after == 5
            assert result.space_reclaimed_bytes > 0

    def test_compact_journal_small_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = os.path.join(tmp, "journal.jsonl")
            with open(journal, "w") as f:
                for i in range(3):
                    f.write(json.dumps({"i": i}) + "\n")

            comp = SnapshotCompactor(tmp, journal)
            result = comp.compact_journal(keep_last_n=10)
            assert result is not None
            with open(journal) as f:
                lines = f.readlines()
            assert len(lines) == 3  # Not trimmed

    def test_prune_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Create some checkpoints
            for name in ["old", "older", "oldest", "recent1", "recent2", "recent3"]:
                with open(os.path.join(tmp, f"ckpt_{name}.json"), "w") as f:
                    json.dump({"name": name}, f)
                # Touch file to set mtime for ordering
                os.utime(os.path.join(tmp, f"ckpt_{name}.json"), (0, 0))

            comp = SnapshotCompactor(tmp, os.path.join(tmp, "journal.jsonl"))
            pruned = comp.prune_checkpoints(keep_last_n=3)
            assert pruned == 3

    def test_compact_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = os.path.join(tmp, "journal.jsonl")
            with open(journal, "w") as f:
                for i in range(20):
                    f.write(json.dumps({"i": i}) + "\n")

            comp = SnapshotCompactor(tmp, journal)
            result = comp.compact_all(keep_journal=5)
            assert result.journal_entries_before == 20
            assert result.journal_entries_after == 5
            assert result.duration_seconds >= 0


# ── Persistence Engine ─────────────────────────────────────────────

class TestPersistenceEngine:
    def test_engine_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            pe = PersistenceEngine(
                storage_dir=tmp,
                checkpoint_dir=os.path.join(tmp, "ckpts"),
                journal_path=os.path.join(tmp, "journal.jsonl"),
            )
            assert hasattr(pe, "graph")
            assert hasattr(pe, "replay")
            assert hasattr(pe, "compactor")

    def test_persist_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = os.path.join(tmp, "journal.jsonl")
            pe = PersistenceEngine(
                storage_dir=tmp,
                checkpoint_dir=os.path.join(tmp, "ckpts"),
                journal_path=journal,
            )

            # Persist a graph
            pe.persist_graph(PersistedGraph(nodes={"n1": {"type": "file"}}))

            # Add events to journal
            with open(journal, "a") as f:
                f.write(json.dumps({"event_type": "build", "sequence": 1}) + "\n")
                f.write(json.dumps({"event_type": "deploy", "sequence": 2}) + "\n")

            # Replay
            replayed = []
            count = pe.replay_execution(lambda e: replayed.append(e.event_type))
            assert count == 2
            assert replayed == ["build", "deploy"]

            # Check status
            status = pe.get_status()
            assert "snapshot_count" in status
            assert "last_sequence" in status

    def test_compaction_from_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = os.path.join(tmp, "journal.jsonl")
            with open(journal, "w") as f:
                for i in range(30):
                    f.write(json.dumps({"i": i}) + "\n")

            pe = PersistenceEngine(
                storage_dir=tmp,
                checkpoint_dir=os.path.join(tmp, "ckpts"),
                journal_path=journal,
            )
            result = pe.run_compaction()
            # compact_all default keep_journal=100, so 30 < 100 means no pruning
            assert result.journal_entries_before == 30
            assert result.journal_entries_after == 30