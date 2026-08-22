from astra.graph.relation_builder import (
    build_dependency_edges,
    deduplicate_edges,
    map_dependency_to_edge,
)
from astra.ir.models import EdgeType, IRDependency, IREdge


def test_dependency_mapping_behavior_equivalence():
    assert map_dependency_to_edge(IRDependency(
        source_file="a.py",
        target_module="b.py",
        kind="import",
    )) == EdgeType.IMPORTS

    assert map_dependency_to_edge(IRDependency(
        source_file="a.py",
        target_module="b.py",
        kind="call",
    )) == EdgeType.CALLS

    assert map_dependency_to_edge(IRDependency(
        source_file="a.py",
        target_module="b.py",
        kind="inheritance",
    )) == EdgeType.EXTENDS


def test_dependency_edge_generation_is_deterministic():
    deps = [
        IRDependency(
            source_file="a.py",
            target_module="b.py",
            kind="import",
            line=10,
        ),
    ]

    edges_1 = build_dependency_edges(deps)
    edges_2 = build_dependency_edges(deps)

    assert edges_1 == edges_2


def test_duplicate_edges_are_removed():
    edges = [
        IREdge(
            from_node="a",
            to_node="b",
            type=EdgeType.IMPORTS,
        ),
        IREdge(
            from_node="a",
            to_node="b",
            type=EdgeType.IMPORTS,
        ),
    ]

    deduped = deduplicate_edges(edges)

    assert len(deduped) == 1


def test_deduplication_is_idempotent():
    edges = [
        IREdge(
            from_node="a",
            to_node="b",
            type=EdgeType.IMPORTS,
        ),
    ]

    once = deduplicate_edges(edges)
    twice = deduplicate_edges(once)

    assert once == twice


def test_empty_targets_are_ignored():
    deps = [
        IRDependency(
            source_file="a.py",
            target_module="",
            kind="import",
        ),
    ]

    assert build_dependency_edges(deps) == []
