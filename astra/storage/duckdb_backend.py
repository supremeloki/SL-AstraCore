from __future__ import annotations

import json
from typing import Sequence, Optional

import duckdb

from astra.ir.models import IRNode, IREdge, NodeType, EdgeType

_NODE_DDL = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    metadata JSON
)
"""

_EDGE_DDL = """
CREATE TABLE IF NOT EXISTS graph_edges (
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    confidence REAL DEFAULT 0.0,
    metadata JSON,
    PRIMARY KEY (from_node, to_node, type)
)
"""


def _node_from_row(row) -> IRNode:
    return IRNode(
        id=row[0],
        type=NodeType[row[1]],
        name=row[2],
        source=row[3],
        confidence=row[4] or 0.0,
        metadata=json.loads(row[5]) if row[5] else {},
    )


def _edge_from_row(row) -> IREdge:
    return IREdge(
        from_node=row[0],
        to_node=row[1],
        type=EdgeType[row[2]],
        weight=row[3] or 1.0,
        confidence=row[4] or 0.0,
        metadata=json.loads(row[5]) if row[5] else {},
    )


class DuckDBBackend:
    """DuckDB persistent graph backend — default production backend."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    def connect(self) -> None:
        self._conn = duckdb.connect(self._db_path)
        self._conn.execute(_NODE_DDL)
        self._conn.execute(_EDGE_DDL)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            raise RuntimeError("DuckDBBackend not connected")
        return self._conn

    def add_node(self, node: IRNode) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO graph_nodes VALUES (?, ?, ?, ?, ?, ?)",
            [node.id, node.type.name, node.name, node.source,
             node.confidence, json.dumps(node.metadata, default=str)],
        )

    def get_node(self, node_id: str) -> Optional[IRNode]:
        rows = self.conn.execute(
            "SELECT * FROM graph_nodes WHERE id = ?", [node_id]
        ).fetchall()
        return _node_from_row(rows[0]) if rows else None

    def delete_node(self, node_id: str) -> None:
        self.conn.execute("DELETE FROM graph_nodes WHERE id = ?", [node_id])
        self.conn.execute(
            "DELETE FROM graph_edges WHERE from_node = ? OR to_node = ?",
            [node_id, node_id],
        )

    def get_all_nodes(self) -> Sequence[IRNode]:
        rows = self.conn.execute("SELECT * FROM graph_nodes").fetchall()
        return [_node_from_row(r) for r in rows]

    def add_edge(self, edge: IREdge) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO graph_edges VALUES (?, ?, ?, ?, ?, ?)",
            [edge.from_node, edge.to_node, edge.type.name,
             edge.weight, edge.confidence, json.dumps(edge.metadata, default=str)],
        )

    def get_edges(
        self,
        from_node: Optional[str] = None,
        to_node: Optional[str] = None,
        edge_type: Optional[EdgeType] = None,
    ) -> Sequence[IREdge]:
        query = "SELECT * FROM graph_edges WHERE 1=1"
        params: list = []
        if from_node:
            query += " AND from_node = ?"
            params.append(from_node)
        if to_node:
            query += " AND to_node = ?"
            params.append(to_node)
        if edge_type:
            query += " AND type = ?"
            params.append(edge_type.name)
        rows = self.conn.execute(query, params).fetchall()
        return [_edge_from_row(r) for r in rows]

    def delete_edge(self, from_node: str, to_node: str, edge_type: object) -> None:
        type_name = edge_type.name if hasattr(edge_type, "name") else str(edge_type)
        self.conn.execute(
            "DELETE FROM graph_edges WHERE from_node = ? AND to_node = ? AND type = ?",
            [from_node, to_node, type_name],
        )

    def get_all_edges(self) -> Sequence[IREdge]:
        rows = self.conn.execute("SELECT * FROM graph_edges").fetchall()
        return [_edge_from_row(r) for r in rows]

    def get_nodes_by_type(self, node_type: NodeType) -> Sequence[IRNode]:
        rows = self.conn.execute(
            "SELECT * FROM graph_nodes WHERE type = ?", [node_type.name]
        ).fetchall()
        return [_node_from_row(r) for r in rows]

    def get_nodes_by_source(self, source: str) -> Sequence[IRNode]:
        rows = self.conn.execute(
            "SELECT * FROM graph_nodes WHERE source = ?", [source]
        ).fetchall()
        return [_node_from_row(r) for r in rows]

    def search_nodes_by_name(self, name_substring: str) -> Sequence[IRNode]:
        rows = self.conn.execute(
            "SELECT * FROM graph_nodes WHERE name LIKE ?",
            [f"%{name_substring}%"],
        ).fetchall()
        return [_node_from_row(r) for r in rows]

    def get_node_ids(self) -> set[str]:
        rows = self.conn.execute("SELECT id FROM graph_nodes").fetchall()
        return {r[0] for r in rows}

    def get_edge_keys(self) -> set[tuple[str, str, str]]:
        rows = self.conn.execute(
            "SELECT from_node, to_node, type FROM graph_edges"
        ).fetchall()
        return {(r[0], r[1], r[2]) for r in rows}

    def node_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]

    def edge_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]