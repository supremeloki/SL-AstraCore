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


def _file_nodes(db_path: str) -> set[str]:
    storage = StorageProvider(backend="duckdb", db_path=db_path).create()
    storage.connect()
    try:
        return {n.id for n in storage.get_all_nodes() if n.type.name == "FILE"}
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
    before_files = _file_nodes(record.db_path)
    assert len(before_files) == 2

    real_read_text = Path.read_text

    def flaky(self, *args, **kwargs):
        if self.name == "a.py":
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky)
    record = orch.index_repo(str(repo))
    monkeypatch.undo()

    after_nodes, after_edges = _counts(record.db_path)
    after_files = _file_nodes(record.db_path)
    assert after_files == before_files, "locked file's node was deleted"
    assert after_nodes >= len(after_files), "nodes vanished"
    assert record.status.value == "active"
    assert record.error is None
    assert any("a.py" in w for w in record.warnings), "the read failure must be reported"

    # The locked file's own import edge must survive: a.py still imports b.py.
    storage = StorageProvider(backend="duckdb", db_path=record.db_path).create()
    storage.connect()
    try:
        a_id = next(nid for nid in after_files if nid.endswith("a.py"))
        b_id = next(nid for nid in after_files if nid.endswith("b.py"))
        assert any(e.from_node == a_id and e.to_node == b_id for e in storage.get_all_edges()), (
            "the locked file's import edge was dropped"
        )
        assert _symbol_names(storage, a_id), "the locked file's symbol nodes were dropped"
    finally:
        storage.close()


def _symbol_names(storage, file_node_id: str) -> set[str]:
    return {n.name for n in storage.get_nodes_by_source("symbol:python") if n.id.startswith(f"{file_node_id}::symbol:")}


def test_genuinely_deleted_file_is_still_reaped(repo):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    record = orch.index_repo(str(repo))
    assert len(_file_nodes(record.db_path)) == 2

    (repo / "b.py").unlink()
    orch.index_repo(str(repo))

    remaining = _file_nodes(record.db_path)
    assert len(remaining) == 1, "a deleted file must still be removed from the graph"
    assert not any(nid.endswith("b.py") for nid in remaining)


def test_parse_failure_is_reported_not_swallowed(repo, monkeypatch):
    orch = RuntimeOrchestrator()
    orch.register_repo(str(repo))
    record = orch.index_repo(str(repo))
    before_files = _file_nodes(record.db_path)

    original = orch._parser_registry.parse

    def exploding(file_path, content):
        if file_path.endswith("b.py"):
            raise ValueError("simulated parser crash")
        return original(file_path, content)

    monkeypatch.setattr(orch._parser_registry, "parse", exploding)
    record = orch.index_repo(str(repo))
    monkeypatch.undo()

    assert _file_nodes(record.db_path) == before_files, "a file whose parser crashed lost its node"
    assert any("b.py" in w for w in record.warnings)
