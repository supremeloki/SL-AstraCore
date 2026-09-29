"""Indexing must never destroy a file's subgraph because of a transient read error.

A file locked by an editor, antivirus or git (WinError 32) raises on read. The
indexer used to swallow that and treat the file as deleted, silently dropping its
nodes and edges while reporting `status=active`. These tests pin the fixed
behaviour: the file keeps its nodes, the run is reported as warning-only, and a
genuinely deleted file is still reaped.
"""

from pathlib import Path

import pytest

from astra.runtime.orchestrator import RuntimeOrchestrator
from astra.storage.backend import StorageProvider


def _counts(db_path: str) -> tuple[int, int]:
    storage = StorageProvider(backend="duckdb", db_path=db_path).create()
    storage.connect()
    try:
        return storage.node_count(), storage.edge_count()
    finally:
        storage.close()


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "a.py").write_text("from b import h\n\ndef f():\n    return h()\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def h():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_locked_file_keeps_its_nodes(repo, monkeypatch):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    record = orch.index_repo(str(repo))
    before_nodes, before_edges = _counts(record.db_path)
    assert before_nodes == 3 and before_edges == 3

    real_read_text = Path.read_text

    def flaky(self, *args, **kwargs):
        if self.name == "a.py":
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky)
    record = orch.index_repo(str(repo))
    monkeypatch.undo()

    after_nodes, after_edges = _counts(record.db_path)
    assert after_nodes == before_nodes, "locked file's nodes were deleted"
    assert after_edges == before_edges, "locked file's edges were deleted"
    assert record.status.value == "active"
    assert record.error is None
    assert any("a.py" in w for w in record.warnings), "the read failure must be reported"


def test_genuinely_deleted_file_is_still_reaped(repo):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    record = orch.index_repo(str(repo))
    assert _counts(record.db_path)[0] == 3

    (repo / "b.py").unlink()
    orch.index_repo(str(repo))

    nodes, _edges = _counts(record.db_path)
    assert nodes == 2, "a deleted file must still be removed from the graph"


def test_parse_failure_is_reported_not_swallowed(repo, monkeypatch):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    orch.index_repo(str(repo))

    original = orch._parser_registry.parse

    def exploding(file_path, content):
        if file_path.endswith("b.py"):
            raise ValueError("simulated parser crash")
        return original(file_path, content)

    monkeypatch.setattr(orch._parser_registry, "parse", exploding)
    record = orch.index_repo(str(repo))
    monkeypatch.undo()

    nodes, _edges = _counts(record.db_path)
    assert nodes == 3, "a file whose parser crashed must keep its nodes"
    assert any("b.py" in w for w in record.warnings)
