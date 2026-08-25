from __future__ import annotations

from typing import Sequence
from astra.context.token_budget import TokenBudget
from astra.ir.models import IRContextPack, IRNode, IREdge, NodeType, ContextNodeRef, ContextEdgeRef

class ContextEngine:
    """Generates a compressed context pack based on graph queries."""

    def __init__(self, storage) -> None:
        self._storage = storage

    def generate_context_pack(
        self,
        query_intent: str,
        seed_nodes: Sequence[str],
        max_tokens: int | None = None,
    ) -> IRContextPack:
        """Slices the graph around seed nodes to form a context pack."""
        ordered: list[str] = []
        visited: set[str] = set()
        for node_id in seed_nodes:
            if node_id not in visited:
                visited.add(node_id)
                ordered.append(node_id)

        # Context engine slice logic:
        # Simple 1-hop reachability slicing (outgoing first, then incoming),
        # preserving discovery order so seeds are considered first.
        for node_id in list(ordered):
            edges = self._storage.get_edges(from_node=node_id)
            for edge in edges:
                if edge.to_node not in visited:
                    visited.add(edge.to_node)
                    ordered.append(edge.to_node)

        # ADDED: Include reverse edges (incoming dependencies) for context completeness
        for node_id in list(ordered):
            edges = self._storage.get_edges(to_node=node_id)
            for edge in edges:
                if edge.from_node not in visited:
                    visited.add(edge.from_node)
                    ordered.append(edge.from_node)

        budget = TokenBudget(max_tokens) if max_tokens is not None else None

        nodes_ref = []
        total_tokens = 0
        included: set[str] = set()
        for n_id in ordered:
            node = self._storage.get_node(n_id)
            if not node:
                continue
            cost = TokenBudget.estimate(f"{node.id} {node.type.name} {node.name}")
            if budget is not None and total_tokens + cost > budget.budget:
                continue
            total_tokens += cost
            included.add(n_id)
            metadata = getattr(node, "metadata", None) or {}
            nodes_ref.append(ContextNodeRef(
                node_id=node.id,
                node_type=node.type,
                name=node.name,
                file_path=getattr(node, "file_path", "") or metadata.get("file_path", ""),
                relevance_score=1.0
            ))

        edges_ref = []
        for n_id in included:
            edges = self._storage.get_edges(from_node=n_id)
            for edge in edges:
                if edge.to_node in included:
                    edges_ref.append(ContextEdgeRef(
                        from_node=edge.from_node,
                        to_node=edge.to_node,
                        edge_type=edge.type
                    ))

        return IRContextPack(
            query_intent=query_intent,
            nodes=tuple(nodes_ref),
            edges=tuple(edges_ref),
            token_budget=max_tokens or 0,
            total_tokens=total_tokens,
            confidence=0.9
        )
