from astra.graph.conflict_enricher import (
    _different_modules,
    detect_circular_dependencies,
    detect_naming_conflicts,
)
from astra.ir.models import IRDependency, IRFileNode, NodeType


def _make_file(path: str) -> IRFileNode:
    return IRFileNode(
        id=f"file:{path}",
        type=NodeType.FILE,
        name=path,
        source="scanner",
        file_path=path,
    )


def test_naming_conflict_detected_across_modules():
    files = [
        _make_file("src/user/model.py"),
        _make_file("src/order/model.py"),
    ]

    conflicts = detect_naming_conflicts(files)

    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.category == "naming"
    assert c.severity == "low"
    assert c.confidence == 0.8


def test_naming_conflict_not_detected_in_same_module():
    files = [
        _make_file("src/model.py"),
        _make_file("src/model.py"),
    ]

    conflicts = detect_naming_conflicts(files)

    assert len(conflicts) == 0


def test_naming_conflict_not_detected_on_unique_names():
    files = [
        _make_file("src/user.py"),
        _make_file("src/order.py"),
    ]

    conflicts = detect_naming_conflicts(files)

    assert len(conflicts) == 0


def test_different_modules_detection():
    assert _different_modules("a/x.py", "b/x.py") is True
    assert _different_modules("a/x.py", "a/y.py") is False


def test_circular_dependency_detected():
    deps = [
        IRDependency(
            source_file="a.py",
            target_module="b.py",
            kind="import",
        ),
        IRDependency(
            source_file="b.py",
            target_module="a.py",
            kind="import",
        ),
    ]
    conflicts = detect_circular_dependencies(deps)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.category == "circular_dependency"
    assert c.severity == "high"
    assert c.confidence == 0.9


def test_no_circular_dependency():
    deps = [
        IRDependency(
            source_file="a.py",
            target_module="b.py",
            kind="import",
        ),
    ]

    assert detect_circular_dependencies(deps) == []


def test_idempotent_conflict_detection():
    deps = [
        IRDependency(source_file="a.py", target_module="b.py", kind="import"),
        IRDependency(source_file="b.py", target_module="a.py", kind="import"),
    ]

    first = detect_circular_dependencies(deps)
    second = detect_circular_dependencies(deps)

    assert first == second