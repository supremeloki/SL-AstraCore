from __future__ import annotations

from typing import Sequence
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
        relevant_nodes = set(seed_nodes)
        
        # Context engine slice logic:
        # Simple 1-hop reachability slicing
        for node_id in list(relevant_nodes):
            edges = self._storage.get_edges(from_node=node_id)
            for edge in edges:
                relevant_nodes.add(edge.to_node)
        
        # ADDED: Include reverse edges (incoming dependencies) for context completeness
        for node_id in list(relevant_nodes):
            edges = self._storage.get_edges(to_node=node_id)
            for edge in edges:
                relevant_nodes.add(edge.from_node)
        
        nodes_ref = []
        for n_id in relevant_nodes:
            node = self._storage.get_node(n_id)
            if node:
                nodes_ref.append(ContextNodeRef(
                    node_id=node.id,
                    node_type=node.type,
                    name=node.name,
                    file_path=getattr(node, 'file_path', ''),
                    relevance_score=1.0
                ))
                
        edges_ref = []
        for n_id in relevant_nodes:
            edges = self._storage.get_edges(from_node=n_id)
            for edge in edges:
                if edge.to_node in relevant_nodes:
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
            confidence=0.9
        )
