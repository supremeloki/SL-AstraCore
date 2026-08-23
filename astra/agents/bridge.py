"""Bridge: legacy ContextPack → IRContextPack."""
from __future__ import annotations

from astra.ir.models import (
    ContextEdgeRef,
    ContextNodeRef,
    EdgeType,
    IRContextPack,
    NodeType,
    TaskType,
)


def legacy_pack_to_ir(legacy_pack) -> IRContextPack:
    ir_nodes = []
    for n in legacy_pack.relevant_nodes:
        raw_type = n.get("type", "file").upper()
        try:
            nt = NodeType[raw_type]
        except KeyError:
            nt = NodeType.FILE

        ir_nodes.append(
            ContextNodeRef(
                node_id=n.get("id", ""),
                node_type=nt,
                name=n.get("label", ""),
                file_path=n.get("file", ""),
                relevance_score=float(n.get("confidence", 0.0)),
            )
        )

    ir_edges = []
    for e in legacy_pack.critical_dependencies:
        raw_type = e.get("type", "DEPENDS_ON").upper()
        try:
            et = EdgeType[raw_type]
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

    try:
        task_type = TaskType[getattr(legacy_pack, "task_type", "analysis").upper()]
    except KeyError:
        task_type = TaskType.ANALYSIS

    return IRContextPack(
        task_summary=getattr(legacy_pack, "task", ""),
        task_type=task_type,
        nodes=tuple(ir_nodes),
        edges=tuple(ir_edges),
        required_files=tuple(legacy_pack.required_files),
        hidden_risks=tuple(legacy_pack.hidden_risks),
        confidence=float(getattr(legacy_pack, "confidence", 0.0)),
        total_tokens=getattr(legacy_pack, "token_estimate", 0),
    )
