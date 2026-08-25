from pathlib import Path

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
    nodes, edges = enrich_graph(files)
    patterns = [n for n in nodes if n.type == NodeType.PATTERN]
    assert any(p.name == "repository" for p in patterns)
    assert any(e.type.name == "IMPLEMENTS" for e in edges)


def test_detects_naming_conflict_windows_paths():
    files = [
        _file(r"C:\repo\a\user_repository.py"),
        _file(r"C:\repo\b\user_repository.py"),
        _file(r"C:\repo\c\other.py"),
    ]
    nodes, edges = enrich_graph(files)
    conflicts = [n for n in nodes if n.type == NodeType.CONFLICT]
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "naming"


def test_naming_convention_detected():
    files = [_file(f"src/mod_{i}/util_helper.py") for i in range(3)]
    files.append(_file("src/Weird-Name.py"))
    nodes, edges = enrich_graph(files)
    patterns = [n for n in nodes if n.type == NodeType.PATTERN]
    assert any(p.name.startswith("naming:") for p in patterns)


def test_empty_input_is_noop():
    assert enrich_graph([]) == ([], [])


def test_edges_reference_existing_files_only():
    files = [_file("repositories/user_repository.py"), _file("repositories/order_repository.py")]
    nodes, edges = enrich_graph(files)
    file_ids = {f"file:{f.file_path}" for f in files}
    for e in edges:
        if e.to_node.startswith("file:"):
            assert e.to_node in file_ids
