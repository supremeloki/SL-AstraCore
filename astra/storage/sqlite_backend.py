from __future__ import annotations

import json
import sqlite3
from typing import Sequence, Optional

from astra.ir.models import IRNode, IREdge, NodeType, EdgeType

_NODE_DDL = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL DEFAULT 0.0,
    metadata TEXT
)
"""

_EDGE_DDL = """
CREATE TABLE IF NOT EXISTS graph_edges (
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    confidence REAL DEFAULT 0.0,
    metadata TEXT,
    PRIMARY KEY (from_node, to_node, type)
)
"""


def _normalize_meta(meta):
    # JSON has no tuples; canonicalize sequences to tuples on both write and
    # read so nodes compare equal across reopen and mutator diffing converges.
    if isinstance(meta, (list, tuple)):
        return tuple(_normalize_meta(v) for v in meta)
    if isinstance(meta, dict):
        return {k: _normalize_meta(v) for k, v in meta.items()}
    return meta


def _node_from_row(row) -> IRNode:
    return IRNode(
        id=row[0],
        type=NodeType[row[1]],
        name=row[2],
        source=row[3],
        confidence=row[4] or 0.0,
        metadata=_normalize_meta(json.loads(row[5])) if row[5] else {},
    )


def _edge_from_row(row) -> IREdge:
    return IREdge(
        from_node=row[0],
        to_node=row[1],
        type=EdgeType[row[2]],
        weight=row[3] or 1.0,
        confidence=row[4] or 0.0,
        metadata=_normalize_meta(json.loads(row[5])) if row[5] else {},
    )


class SQLiteBackend:
    """SQLite persistent graph backend — fallback and metadata store."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = None
        self._conn.isolation_level = None  # autocommit on by default
        self._conn.execute(_NODE_DDL)
        self._conn.execute(_EDGE_DDL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteBackend not connected")
        return self._conn

    # CRUD (no auto-commit; transaction handles it)
    def add_node(self, node: IRNode) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO graph_nodes VALUES (?, ?, ?, ?, ?, ?)",
            [node.id, node.type.name, node.name, node.source,
             node.confidence,
             json.dumps(_normalize_meta(node.metadata), default=str)],
        )

    def get_node(self, node_id: str) -> Optional[IRNode]:
        cur = self.conn.execute(
            "SELECT * FROM graph_nodes WHERE id = ?", [node_id]
        )
        row = cur.fetchone()
        return _node_from_row(row) if row else None

    def delete_node(self, node_id: str) -> None:
        self.conn.execute("DELETE FROM graph_nodes WHERE id = ?", [node_id])
        self.conn.execute(
            "DELETE FROM graph_edges WHERE from_node = ? OR to_node = ?",
            [node_id, node_id],
        )

    def get_all_nodes(self) -> Sequence[IRNode]:
        cur = self.conn.execute("SELECT * FROM graph_nodes")
        return [_node_from_row(r) for r in cur.fetchall()]

    def add_edge(self, edge: IREdge) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO graph_edges VALUES (?, ?, ?, ?, ?, ?)",
            [edge.from_node, edge.to_node, edge.type.name,
             edge.weight, edge.confidence,
             json.dumps(_normalize_meta(edge.metadata), default=str)],
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
        cur = self.conn.execute(query, params)
        return [_edge_from_row(r) for r in cur.fetchall()]

    def delete_edge(self, from_node: str, to_node: str, edge_type: object) -> None:
        type_name = edge_type.name if hasattr(edge_type, "name") else str(edge_type)
        self.conn.execute(
            "DELETE FROM graph_edges WHERE from_node = ? AND to_node = ? AND type = ?",
            [from_node, to_node, type_name],
        )

    def get_all_edges(self) -> Sequence[IREdge]:
        cur = self.conn.execute("SELECT * FROM graph_edges")
        return [_edge_from_row(r) for r in cur.fetchall()]

    def get_nodes_by_type(self, node_type: NodeType) -> Sequence[IRNode]:
        cur = self.conn.execute(
            "SELECT * FROM graph_nodes WHERE type = ?", [node_type.name]
        )
        return [_node_from_row(r) for r in cur.fetchall()]

    def get_nodes_by_source(self, source: str) -> Sequence[IRNode]:
        cur = self.conn.execute(
            "SELECT * FROM graph_nodes WHERE source = ?", [source]
        )
        return [_node_from_row(r) for r in cur.fetchall()]

    def search_nodes_by_name(self, name_substring: str) -> Sequence[IRNode]:
        escaped = name_substring.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        cur = self.conn.execute(
            "SELECT * FROM graph_nodes WHERE name LIKE ? ESCAPE '\\'",
            [f"%{escaped}%"],
        )
        return [_node_from_row(r) for r in cur.fetchall()]

    def get_node_ids(self) -> set[str]:
        cur = self.conn.execute("SELECT id FROM graph_nodes")
        return {r[0] for r in cur.fetchall()}

    def get_edge_keys(self) -> set[tuple[str, str, str]]:
        cur = self.conn.execute(
            "SELECT from_node, to_node, type FROM graph_edges"
        )
        return {(r[0], r[1], r[2]) for r in cur.fetchall()}

    def node_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]

    def edge_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]

    # Batch operations (Phase 2 hardened)
    def add_nodes(self, nodes: Sequence[IRNode]) -> None:
        if not nodes:
            return
        self.conn.executemany(
            "INSERT OR REPLACE INTO graph_nodes VALUES (?, ?, ?, ?, ?, ?)",
            [(n.id, n.type.name, n.name, n.source,
              n.confidence, json.dumps(_normalize_meta(n.metadata), default=str))
             for n in nodes],
        )

    def add_edges(self, edges: Sequence[IREdge]) -> None:
        if not edges:
            return
        self.conn.executemany(
            "INSERT OR REPLACE INTO graph_edges VALUES (?, ?, ?, ?, ?, ?)",
            [(e.from_node, e.to_node, e.type.name,
              e.weight, e.confidence, json.dumps(_normalize_meta(e.metadata), default=str))
             for e in edges],
        )

    def transaction(self) -> "_SQLiteTransaction":
        return _SQLiteTransaction(self)


class _SQLiteTransaction:
    """Atomic transaction context for SQLite."""

    def __init__(self, backend: "SQLiteBackend") -> None:
        self._backend = backend
        self._committed = False

    def __enter__(self) -> "_SQLiteTransaction":
        self._backend.conn.isolation_level = "DEFERRED"
        self._backend.conn.execute("BEGIN")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if exc_type is None and not self._committed:
                self._backend.conn.commit()
                self._committed = True
            elif exc_type is not None:
                self._backend.conn.rollback()
        finally:
            self._backend.conn.isolation_level = None

    def commit(self) -> None:
        if not self._committed:
            self._backend.conn.commit()
            self._committed = True

    def rollback(self) -> None:
        if not self._committed:
            self._backend.conn.rollback()
            self._committed = True