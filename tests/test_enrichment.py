import logging
from pathlib import Path

from astra.graph import enrichment
from astra.graph.enrichment import enrich_graph
from astra.ir.models import IRFileNode, NodeType


def _file(path: str) -> IRFileNode:
    return IRFileNode(
        id=f"file:{path}",
        type=NodeType.FILE,
        name=Path(path).name,
        source="test",
        file_path=path,
    )


def test_detects_repository_pattern():
    files = [_file("src/repositories/user_repository.py"), _file("src/repositories/order_repository.py")]
    nodes, edges, warnings = enrich_graph(files)
    patterns = [n for n in nodes if n.type == NodeType.PATTERN]
    assert any(p.name == "repository" for p in patterns)
    assert any(e.type.name == "IMPLEMENTS" for e in edges)
    assert warnings == []


def test_detects_naming_conflict_windows_paths():
    files = [
        _file(r"C:\repo\a\user_repository.py"),
        _file(r"C:\repo\b\user_repository.py"),
        _file(r"C:\repo\c\other.py"),
    ]
    nodes, edges, _ = enrich_graph(files)
    conflicts = [n for n in nodes if n.type == NodeType.CONFLICT]
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "naming"


def test_naming_convention_detected():
    files = [_file(f"src/mod_{i}/util_helper.py") for i in range(3)]
    files.append(_file("src/Weird-Name.py"))
    nodes, edges, _ = enrich_graph(files)
    patterns = [n for n in nodes if n.type == NodeType.PATTERN]
    assert any(p.name.startswith("naming:") for p in patterns)


def test_empty_input_is_noop():
    assert enrich_graph([]) == ([], [], [])


def test_edges_reference_existing_files_only():
    files = [_file("repositories/user_repository.py"), _file("repositories/order_repository.py")]
    nodes, edges, _ = enrich_graph(files)
    file_ids = {f"file:{f.file_path}" for f in files}
    for e in edges:
        if e.to_node.startswith("file:"):
            assert e.to_node in file_ids


def test_nothing_to_enrich_is_silent_and_normal(monkeypatch):
    """Genuinely no patterns/conflicts: empty result, no warning, no error."""
    monkeypatch.setattr(enrichment, "detect_design_patterns", lambda nodes: [])
    monkeypatch.setattr(enrichment, "detect_naming_conventions", lambda nodes: [])
    monkeypatch.setattr(enrichment, "detect_naming_conflicts", lambda nodes: [])

    nodes, edges, warnings = enrich_graph([_file("src/plain.py")])

    assert (nodes, edges) == ([], [])
    assert warnings == []


def test_enrichment_crash_is_reported_not_swallowed(monkeypatch, caplog):
    """A bug inside enrichment must never be indistinguishable from 'nothing found'."""
    def boom(_nodes):
        raise RuntimeError("pattern matcher blew up")

    monkeypatch.setattr(enrichment, "detect_design_patterns", boom)

    with caplog.at_level(logging.WARNING, logger="astra.graph.enrichment"):
        nodes, edges, warnings = enrich_graph([_file("src/repositories/user_repository.py")])

    assert (nodes, edges) == ([], []), "must not raise out of enrich_graph"
    assert warnings, "an enrichment crash must be reported, not silently swallowed"
    assert "pattern matcher blew up" in warnings[0]
    assert "RuntimeError" in warnings[0]
    assert any("enrichment failed" in r.message for r in caplog.records), (
        "the failure must be logged, not just returned"
    )


def test_enrichment_crash_surfaces_on_repo_record(tmp_path, monkeypatch):
    """End-to-end: the orchestrator carries the reason into record.warnings,
    which the dashboard already renders."""
    from astra.runtime.orchestrator import RuntimeOrchestrator

    (tmp_path / "a.py").write_text("def f():\n    pass\n", encoding="utf-8")
    orch = RuntimeOrchestrator()
    orch.register_repo(str(tmp_path))

    def boom(_nodes):
        raise ValueError("broken pattern matcher")

    monkeypatch.setattr(enrichment, "detect_design_patterns", boom)

    result = orch.index_repo(str(tmp_path))

    assert result.status.value == "active", "indexing must still succeed"
    assert any("enrichment failed" in w for w in result.warnings), (
        "the dashboard would show an empty graph with no explanation"
    )
