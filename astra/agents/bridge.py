"""Bridge: legacy ContextPack → IRContextPack.

Allows AstraCore (which still uses legacy context_engine.ContextEngine)
to feed the canonical AgentAdapterLayer without modifying either side.

This bridge will be deleted once AstraCore fully migrates to
astra.context.engine.ContextEngine (IRContextPack-native).
"""
from __future__ import annotations

from astra.ir.models import (
    ContextEdgeRef,
    ContextNodeRef,
    EdgeType,
    IRContextPack,
    IRConflictNode,
    IRDecisionNode,
    IRPatternNode,
    IRVaultConceptNode,
    NodeType,
    RiskLevel,
    TaskType,
)


def legacy_pack_to_ir(legacy_pack) -> IRContextPack:
    """Convert a legacy ContextPack (astra.models.context_pack) to IRContextPack."""
    # ── Nodes ──
    ir_nodes: list[ContextNodeRef] = []
    for n in legacy_pack.relevant_nodes:
        node_id = n.get("id", "")
        label = n.get("label", "")
        raw_type = n.get("type", "file").lower()
        try:
            nt = NodeType[raw_type.upper()]
        except KeyError:
            nt = NodeType.FILE
        ir_nodes.append(
            ContextNodeRef(
                node_id=node_id,
                node_type=nt,
                name=label,
                file_path=n.get("file", ""),
                snippet=n.get("snippet", ""),
                relevance_score=float(n.get("confidence", 0.0)),
            )
        )

    # ── Edges ──
    ir_edges: list[ContextEdgeRef] = []
    for e in legacy_pack.critical_dependencies:
        raw_etype = e.get("type", "depends_on").upper()
        try:
            et = EdgeType[raw_etype]
        except KeyError:
            et = EdgeType.DEPENDS_ON
        ir_edges.append(
            ContextEdgeRef(
                from_node=e.get("from", ""),
                to_node=e.get("to", ""),
                edge_type=et,
                weight=float(e.get("weight", 1.0)),
            )
        )

    # ── Task type ──
    raw_task_type = getattr(legacy_pack, "task_type", "analysis").upper()
    try:
        tt = TaskType[raw_task_type]
    except KeyError:
        tt = TaskType.ANALYSIS

    # ── Vault concepts / decisions / patterns / conflicts ──
    vault_concepts: tuple[IRVaultConceptNode, ...] = ()
    decisions: tuple[IRDecisionNode, ...] = ()
    patterns: tuple[IRPatternNode, ...] = ()
    conflicts: tuple[IRConflictNode, ...] = ()

    return IRContextPack(
        task_summary=getattr(legacy_pack, "task", ""),
        task_type=tt,
        query_intent="",
        nodes=tuple(ir_nodes),
        edges=tuple(ir_edges),
        vault_context=vault_concepts,
        decisions=decisions,
        patterns=patterns,
        conflicts=conflicts,
        required_files=tuple(legacy_pack.required_files),
        dependency_summary=tuple(str(d) for d in legacy_pack.critical_dependencies),
        hidden_risks=tuple(legacy_pack.hidden_risks),
        total_tokens=getattr(legacy_pack, "token_estimate", 0),
        token_budget=0,
        confidence=float(getattr(legacy_pack, "confidence", 0.0)),
    )
