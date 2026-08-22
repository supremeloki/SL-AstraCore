from __future__ import annotations

from typing import Sequence

from astra.ir.models import (
    EdgeType,
    IREdge,
    IRNode,
    IRVaultConceptNode,
    VaultConceptKind,
)


VAULT_KIND_TO_EDGE: dict[VaultConceptKind, EdgeType] = {
    VaultConceptKind.DECISION: EdgeType.REFERENCES,
    VaultConceptKind.ARCHITECTURE: EdgeType.REFERENCES,
    VaultConceptKind.RULE: EdgeType.REFERENCES,
    VaultConceptKind.WARNING: EdgeType.REFERENCES,
    VaultConceptKind.IDEA: EdgeType.REFERENCES,
    VaultConceptKind.NOTE: EdgeType.REFERENCES,
    VaultConceptKind.RFC: EdgeType.REFERENCES,
    VaultConceptKind.TODO: EdgeType.REFERENCES,
    VaultConceptKind.DESIGN: EdgeType.REFERENCES,
}


def build_vault_code_edges(
    vault_concepts: Sequence[IRVaultConceptNode],
    code_nodes: Sequence[IRNode],
) -> Sequence[IREdge]:
    code_node_ids = {node.id for node in code_nodes}
    edges = []

    for concept in vault_concepts:
        for code_path in concept.linked_code_paths:
            if code_path in code_node_ids:
                edges.append(IREdge(
                    from_node=concept.id,
                    to_node=code_path,
                    type=VAULT_KIND_TO_EDGE.get(concept.concept_type, EdgeType.REFERENCES),
                    weight=concept.strength,
                    confidence=concept.confidence,
                ))
    return edges


def build_vault_concept_edges(
    vault_concepts: Sequence[IRVaultConceptNode],
) -> Sequence[IREdge]:
    concept_ids = {c.id for c in vault_concepts}
    edges = []

    for concept in vault_concepts:
        for related_name in concept.related_concepts:
            related_id = f"vault:{related_name}"
            if related_id in concept_ids and related_id != concept.id:
                edges.append(IREdge(
                    from_node=concept.id,
                    to_node=related_id,
                    type=EdgeType.LINKS_TO,
                    weight=concept.strength,
                    confidence=concept.confidence,
                ))
    return edges


def detect_orphan_vault_concepts(
    vault_concepts: Sequence[IRVaultConceptNode],
    code_nodes: Sequence[IRNode],
) -> Sequence[str]:
    code_node_ids = {node.id for node in code_nodes}
    orphans = []

    for concept in vault_concepts:
        has_code_link = any(
            path in code_node_ids
            for path in concept.linked_code_paths
        )
        has_concept_link = any(
            f"vault:{name}" in {c.id for c in vault_concepts}
            for name in concept.related_concepts
        )
        if not has_code_link and not has_concept_link:
            orphans.append(concept.id)
    return orphans


def deduplicate_edges(edges: Sequence[IREdge]) -> Sequence[IREdge]:
    seen: set[tuple[str, str, EdgeType]] = set()
    deduped: list[IREdge] = []
    for edge in edges:
        key = (edge.from_node, edge.to_node, edge.type)
        if key not in seen:
            seen.add(key)
            deduped.append(edge)
    return deduped