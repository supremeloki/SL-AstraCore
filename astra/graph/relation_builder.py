from __future__ import annotations

from typing import Sequence

from astra.ir.models import EdgeType, IREdge, IRDependency


DEPENDENCY_TO_EDGE: dict[str, EdgeType] = {
    "import": EdgeType.IMPORTS,
    "call": EdgeType.CALLS,
    "inheritance": EdgeType.EXTENDS,
    "composition": EdgeType.DEPENDS_ON,
    "implementation": EdgeType.IMPLEMENTS,
    "reference": EdgeType.REFERENCES,
}


def map_dependency_to_edge(dep: IRDependency) -> EdgeType:
    return DEPENDENCY_TO_EDGE.get(dep.kind, EdgeType.DEPENDS_ON)


def build_dependency_edges(deps: Sequence[IRDependency]) -> Sequence[IREdge]:
    edges = []
    for dep in deps:
        source = dep.source_file
        target = dep.resolved_target or dep.target_module
        if not source or not target:
            continue
        edges.append(IREdge(
            from_node=source,
            to_node=target,
            type=map_dependency_to_edge(dep),
            weight=1.0,
            metadata={"line": dep.line},
        ))
    return edges


def deduplicate_edges(edges: Sequence[IREdge]) -> Sequence[IREdge]:
    seen: set[tuple[str, str, EdgeType]] = set()
    deduped: list[IREdge] = []
    for edge in edges:
        key = (edge.from_node, edge.to_node, edge.type)
        if key not in seen:
            seen.add(key)
            deduped.append(edge)
    return deduped
