from __future__ import annotations

from typing import Sequence, Optional
from astra.ir.models import IRNode, IREdge
from astra.graph.storage_api import GraphStorageAdapter

class InMemoryGraphStorage:
    """In-memory implementation of GraphStorageAdapter."""
    
    def __init__(self) -> None:
        self._nodes: dict[str, IRNode] = {}
        self._edges: list[IREdge] = []
        
    def connect(self) -> None: pass
    def close(self) -> None: pass
    
    def add_node(self, node: IRNode) -> None:
        self._nodes[node.id] = node
        
    def get_node(self, node_id: str) -> Optional[IRNode]:
        return self._nodes.get(node_id)
        
    def delete_node(self, node_id: str) -> None:
        if node_id in self._nodes:
            del self._nodes[node_id]
        self._edges = [e for e in self._edges if e.from_node != node_id and e.to_node != node_id]
            
    def add_edge(self, edge: IREdge) -> None:
        self._edges.append(edge)

    def delete_edge(self, from_node: str, to_node: str, edge_type: object) -> None:
        self._edges = [
            e for e in self._edges
            if not (e.from_node == from_node and e.to_node == to_node and e.type == edge_type)
        ]
        
    def get_edges(self, from_node: Optional[str] = None, to_node: Optional[str] = None) -> Sequence[IREdge]:
        results = self._edges
        if from_node:
            results = [e for e in results if e.from_node == from_node]
        if to_node:
            results = [e for e in results if e.to_node == to_node]
        return results
        
    def get_all_nodes(self) -> Sequence[IRNode]:
        return list(self._nodes.values())
        
    def get_all_edges(self) -> Sequence[IREdge]:
        return self._edges
