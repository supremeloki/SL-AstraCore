from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from astra.ir.models import (
    EdgeType,
    IREdge,
    IRNode,
    NodeType,
)


@dataclass(frozen=True)
class QueryResult:
    """Result of a graph query."""
    nodes: tuple[IRNode, ...] = ()
    edges: tuple[IREdge, ...] = ()
    count: int = 0

    def __len__(self) -> int:
        return self.count


class GraphQueryEngine:
    """Query engine over a persistent graph storage backend.

    All queries are deterministic, backend-agnostic, and
    operate exclusively on Canonical IR types.
    """

    def __init__(self, storage) -> None:
        self._storage = storage

    # ── File / Node queries ─────────────────────────────────

    def find_file(self, file_path: str) -> Optional[IRNode]:
        file_id = f"file:{file_path}"
        return self._storage.get_node(file_id)

    def find_named_symbol(self, name: str, node_type: Optional[NodeType] = None) -> QueryResult:
        matches = self._storage.search_nodes_by_name(name)
        if node_type:
            matches = [n for n in matches if n.type == node_type]
        return QueryResult(nodes=tuple(matches), count=len(matches))

    def find_by_type(self, node_type: NodeType) -> QueryResult:
        nodes = self._storage.get_nodes_by_type(node_type)
        return QueryResult(nodes=tuple(nodes), count=len(nodes))

    def find_by_source(self, source: str) -> QueryResult:
        nodes = self._storage.get_nodes_by_source(source)
        return QueryResult(nodes=tuple(nodes), count=len(nodes))

    # ── Dependency queries ─────────────────────────────────

    def find_dependents(self, node_id: str) -> QueryResult:
        """Nodes that depend on node_id (incoming IMPORTS edges)."""
        edges = self._storage.get_edges(to_node=node_id, edge_type=EdgeType.IMPORTS)
        node_ids = {e.from_node for e in edges}
        nodes = [self._storage.get_node(nid) for nid in node_ids if self._storage.get_node(nid)]
        return QueryResult(nodes=tuple(nodes), edges=tuple(edges), count=len(edges))

    def find_imports(self, node_id: str) -> QueryResult:
        """What node_id imports (outgoing IMPORTS edges)."""
        edges = self._storage.get_edges(from_node=node_id, edge_type=EdgeType.IMPORTS)
        node_ids = {e.to_node for e in edges}
        nodes = [self._storage.get_node(nid) for nid in node_ids if self._storage.get_node(nid)]
        return QueryResult(nodes=tuple(nodes), edges=tuple(edges), count=len(edges))

    def find_all_edges_for(self, node_id: str) -> QueryResult:
        incoming = self._storage.get_edges(to_node=node_id)
        outgoing = self._storage.get_edges(from_node=node_id)
        all_edges = list(incoming) + list(outgoing)

        all_ids = set()
        for e in all_edges:
            all_ids.add(e.from_node)
            all_ids.add(e.to_node)
        nodes = [self._storage.get_node(nid) for nid in all_ids if self._storage.get_node(nid)]

        return QueryResult(nodes=tuple(nodes), edges=tuple(all_edges), count=len(all_edges))

    # ── Traversal ──────────────────────────────────────────

    def bfs(self, seed_node_id: str, max_depth: int = 2) -> QueryResult:
        """Breadth-first traversal from a seed node."""
        from collections import deque

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()
        queue.append((seed_node_id, 0))

        result_nodes: list[IRNode] = []
        result_edges: list[IREdge] = []

        while queue:
            current_id, depth = queue.popleft()

            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)

            node = self._storage.get_node(current_id)
            if node:
                result_nodes.append(node)

            if depth < max_depth:
                edges = self._storage.get_edges(from_node=current_id)
                for e in edges:
                    result_edges.append(e)
                    if e.to_node not in visited:
                        queue.append((e.to_node, depth + 1))

        return QueryResult(
            nodes=tuple(result_nodes),
            edges=tuple(result_edges),
            count=len(result_nodes),
        )

    # ── Aggregation ────────────────────────────────────────

    def node_count(self) -> int:
        return self._storage.node_count()

    def edge_count(self) -> int:
        return self._storage.edge_count()

    def edge_type_summary(self) -> dict[str, int]:
        edges = self._storage.get_all_edges()
        summary: dict[str, int] = {}
        for e in edges:
            key = e.type.name
            summary[key] = summary.get(key, 0) + 1
        return summary

    def language_summary(self) -> dict[str, int]:
        nodes = self._storage.get_all_nodes()
        summary: dict[str, int] = {}
        for n in nodes:
            lang = n.metadata.get("language", "unknown")
            summary[lang] = summary.get(lang, 0) + 1
        return summary