from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Optional
from astra.ir.models import IRNode, IREdge


@dataclass(frozen=True)
class GraphMutationResult:
    """Result of applying a mutation to the graph."""
    added_nodes: int = 0
    updated_nodes: int = 0
    removed_nodes: int = 0
    added_edges: int = 0
    updated_edges: int = 0
    removed_edges: int = 0


class GraphMutator:
    """Handles deterministic incremental mutations on a graph storage."""
    
    def __init__(self, storage) -> None:
        self._storage = storage
        
    def apply_node_upsert(self, node: IRNode) -> GraphMutationResult:
        """Add or update a node deterministically."""
        existing = self._storage.get_node(node.id)
        
        if existing is None:
            self._storage.add_node(node)
            return GraphMutationResult(added_nodes=1)
        
        if existing != node:
            self._storage.add_node(node)
            return GraphMutationResult(updated_nodes=1)
            
        return GraphMutationResult()
        
    def apply_node_delete(self, node_id: str) -> GraphMutationResult:
        """Delete a node and its associated edges."""
        existing = self._storage.get_node(node_id)
        
        if existing is None:
            return GraphMutationResult()
            
        edges_from = self._storage.get_edges(from_node=node_id)
        edges_to = self._storage.get_edges(to_node=node_id)
        # A self-loop appears in both directions; count/delete it once.
        seen = {(e.from_node, e.to_node, e.type) for e in edges_from}
        edges_to_remove = list(edges_from) + [
            e for e in edges_to if (e.from_node, e.to_node, e.type) not in seen
        ]
        
        self._storage.delete_node(node_id)
        
        return GraphMutationResult(
            removed_nodes=1,
            removed_edges=len(edges_to_remove)
        )
        
    def apply_edge_upsert(self, edge: IREdge) -> GraphMutationResult:
        """Add or update an edge deterministically."""
        existing_edges = self._storage.get_edges(from_node=edge.from_node, to_node=edge.to_node)
        
        matching = [
            e for e in existing_edges 
            if e.type == edge.type
        ]
        
        if not matching:
            self._storage.add_edge(edge)
            return GraphMutationResult(added_edges=1)
            
        if matching[0] != edge:
            self._storage.add_edge(edge)
            return GraphMutationResult(updated_edges=1)
            
        return GraphMutationResult()
        
    def apply_edge_delete(self, from_node: str, to_node: str, edge_type) -> GraphMutationResult:
        """Delete edges matching criteria."""
        existing = self._storage.get_edges(from_node=from_node, to_node=to_node)
        to_remove = [e for e in existing if e.type == edge_type]
        
        if not to_remove:
            return GraphMutationResult()
            
        for edge in to_remove:
            self._storage.delete_edge(edge.from_node, edge.to_node, edge.type)
            
        return GraphMutationResult(removed_edges=len(to_remove))

    def apply_batch(
        self,
        nodes_to_upsert: Sequence[IRNode] = (),
        nodes_to_delete: Sequence[str] = (),
        edges_to_upsert: Sequence[IREdge] = (),
        edges_to_delete: Sequence[tuple[str, str, object]] = (),
    ) -> GraphMutationResult:
        """Apply a batch of mutations atomically."""
        total = GraphMutationResult()

        with self._storage.transaction():
            for node in nodes_to_delete:
                total = self._merge(total, self.apply_node_delete(node))

            if nodes_to_upsert and hasattr(self._storage, "add_nodes"):
                existing_ids = self._storage.get_node_ids()
                self._storage.add_nodes(nodes_to_upsert)
                for node in nodes_to_upsert:
                    if node.id in existing_ids:
                        total = self._merge(total, GraphMutationResult(updated_nodes=1))
                    else:
                        total = self._merge(total, GraphMutationResult(added_nodes=1))
            else:
                for node in nodes_to_upsert:
                    total = self._merge(total, self.apply_node_upsert(node))

            for edge in edges_to_delete:
                total = self._merge(total, self.apply_edge_delete(*edge))

            if edges_to_upsert and hasattr(self._storage, "add_edges"):
                existing_edges = self._storage.get_edge_keys()
                self._storage.add_edges(edges_to_upsert)
                for edge in edges_to_upsert:
                    key = (edge.from_node, edge.to_node, edge.type.name)
                    if key in existing_edges:
                        total = self._merge(total, GraphMutationResult(updated_edges=1))
                    else:
                        total = self._merge(total, GraphMutationResult(added_edges=1))
            else:
                for edge in edges_to_upsert:
                    total = self._merge(total, self.apply_edge_upsert(edge))

        return total
        
    def _merge(self, a: GraphMutationResult, b: GraphMutationResult) -> GraphMutationResult:
        return GraphMutationResult(
            added_nodes=a.added_nodes + b.added_nodes,
            updated_nodes=a.updated_nodes + b.updated_nodes,
            removed_nodes=a.removed_nodes + b.removed_nodes,
            added_edges=a.added_edges + b.added_edges,
            updated_edges=a.updated_edges + b.updated_edges,
            removed_edges=a.removed_edges + b.removed_edges,
        )


def compute_diff(
    old_nodes: dict[str, IRNode],
    new_nodes: dict[str, IRNode],
) -> tuple[list[IRNode], list[str]]:
    """Compute node diff: (nodes_to_upsert, nodes_to_delete)."""
    old_keys = set(old_nodes.keys())
    new_keys = set(new_nodes.keys())
    
    to_delete = list(old_keys - new_keys)
    to_upsert = [new_nodes[k] for k in (new_keys & old_keys) if old_nodes[k] != new_nodes[k]]
    to_upsert.extend(new_nodes[k] for k in new_keys - old_keys)
    
    return to_upsert, to_delete


def compute_edge_diff(
    old_edges: list[IREdge],
    new_edges: list[IREdge],
) -> tuple[list[IREdge], list[tuple[str, str, object]]]:
    """Compute edge diff: (edges_to_upsert, edges_to_delete)."""
    def edge_key(e: IREdge) -> tuple[str, str, object]:
        return (e.from_node, e.to_node, e.type)
        
    old_map = {edge_key(e): e for e in old_edges}
    new_map = {edge_key(e): e for e in new_edges}
    
    old_keys = set(old_map.keys())
    new_keys = set(new_map.keys())
    
    to_delete = list(old_keys - new_keys)
    to_upsert = [new_map[k] for k in (new_keys & old_keys) if old_map[k] != new_map[k]]
    to_upsert.extend(new_map[k] for k in new_keys - old_keys)
    
    return to_upsert, to_delete