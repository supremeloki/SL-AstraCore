from __future__ import annotations

from typing import Sequence

from astra.ir.models import (
    EdgeType,
    IREdge,
    IRFileNode,
    IRNode,
    IRConflictNode,
    IRPatternNode,
    NodeType,
    RiskLevel,
)
from astra.graph.pattern_enricher import PatternMatch, detect_design_patterns, detect_naming_conventions
from astra.graph.conflict_enricher import ConflictMatch, detect_naming_conflicts


def _pattern_id(match: PatternMatch) -> str:
    return f"pattern:{match.name}"


def _conflict_id(match: ConflictMatch) -> str:
    return f"conflict:{match.category}:{hash((match.source_a, match.source_b)) & 0xFFFFFFFF:x}"


def build_pattern_nodes(patterns: Sequence[PatternMatch]) -> list[IRPatternNode]:
    return [
        IRPatternNode(
            id=_pattern_id(p),
            type=NodeType.PATTERN,
            name=p.name,
            source="pattern-enricher",
            confidence=p.confidence,
            pattern_type=p.name,
            occurrences=len(p.locations),
            locations=p.locations,
        )
        for p in patterns
    ]


def build_conflict_nodes(conflicts: Sequence[ConflictMatch]) -> list[IRConflictNode]:
    severity = {"low": RiskLevel.LOW, "medium": RiskLevel.MEDIUM, "high": RiskLevel.HIGH}
    nodes = []
    for c in conflicts:
        nodes.append(IRConflictNode(
            id=_conflict_id(c),
            type=NodeType.CONFLICT,
            name=f"{c.category}: {c.source_a} <-> {c.source_b}",
            source="conflict-enricher",
            confidence=c.confidence,
            source_a=c.source_a,
            source_b=c.source_b,
            conflict_type=c.category,
            severity=severity.get(c.severity, RiskLevel.MEDIUM),
            evidence=c.description,
        ))
    return nodes


def build_enrichment_edges(
    pattern_nodes: Sequence[IRPatternNode],
    conflict_nodes: Sequence[IRConflictNode],
    file_ids: set[str],
) -> list[IREdge]:
    edges: list[IREdge] = []

    def file_node_id(path: str) -> str | None:
        nid = f"file:{path}"
        if nid in file_ids:
            return nid
        # Windows-style paths stored with backslashes; try normalized too.
        alt = f"file:{path.replace('/', chr(92))}" if "/" in path else None
        return alt if alt in file_ids else None

    for p in pattern_nodes:
        for loc in p.locations:
            target = file_node_id(loc)
            if target:
                edges.append(IREdge(
                    from_node=p.id,
                    to_node=target,
                    type=EdgeType.IMPLEMENTS,
                    weight=p.confidence,
                    confidence=p.confidence,
                ))

    for c in conflict_nodes:
        for endpoint in (c.source_a, c.source_b):
            target = file_node_id(endpoint)
            if target and target != f"file:{endpoint if endpoint == c.source_a else c.source_a}":
                edges.append(IREdge(
                    from_node=c.id,
                    to_node=target,
                    type=EdgeType.DEPENDS_ON,
                    weight=c.confidence,
                    confidence=c.confidence,
                    metadata={"role": "conflict_endpoint"},
                ))

    # dedupe on (from, to, type)
    seen: set[tuple[str, str, EdgeType]] = set()
    deduped = []
    for e in edges:
        key = (e.from_node, e.to_node, e.type)
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    return deduped


def enrich_graph(
    parse_results: Sequence[IRFileNode],
) -> tuple[list[IRNode], list[IREdge]]:
    """Run pattern + conflict detection over parsed files.

    Returns extra nodes/edges to merge into the index batch. Never raises —
    enrichment is best-effort and must not break indexing.
    """
    file_nodes = [r for r in parse_results if r.file_path]
    if not file_nodes:
        return [], []
    try:
        patterns = [
            *detect_design_patterns(file_nodes),
            *detect_naming_conventions(file_nodes),
        ]
        conflicts = [*detect_naming_conflicts(file_nodes)]

        pattern_nodes = build_pattern_nodes(patterns)
        conflict_nodes = build_conflict_nodes(conflicts)

        file_ids = {f"file:{n.file_path}" for n in file_nodes}
        edges = build_enrichment_edges(pattern_nodes, conflict_nodes, file_ids)
        return [*pattern_nodes, *conflict_nodes], edges
    except Exception:
        return [], []
