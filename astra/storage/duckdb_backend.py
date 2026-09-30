from __future__ import annotations

import json
from typing import Sequence, Optional

import duckdb

from astra.ir.models import IRNode, IREdge, NodeType, EdgeType
from astra.storage import sql_base

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


def _dedupe_by_key(rows: list[list[object]], columns: list[str], keys: list[str]) -> list[list[object]]:
    # Duplicate keys within one batch crash the set-based upsert (DELETE then
    # INSERT violates the PK); keep last occurrence, matching INSERT OR REPLACE.
    if len(rows) < 2:
        return rows
    key_idx = [columns.index(k) for k in keys]
    dedup: dict[tuple, list[object]] = {}
    for r in rows:
        dedup[tuple(r[j] for j in key_idx)] = r
    return list(dedup.values())


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


_list_cast_warmed = False


def _warm_list_cast(conn: "duckdb.DuckDBPyConnection") -> None:
    # First list-cast unnest in a duckdb 1.5.x process costs 10-20s of one-time
    # codegen. Warm it lazily once so every subsequent batch write is ms-fast.
    global _list_cast_warmed
    if not _list_cast_warmed:
        conn.execute("SELECT unnest(?::VARCHAR[])", [["__astra_warmup__"]])
        _list_cast_warmed = True


class DuckDBBackend:
    """DuckDB persistent graph backend — default production backend."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self._column_cache: dict[str, list[str]] = {}

    def connect(self) -> None:
        self._conn = duckdb.connect(self._db_path)
        self._column_cache.clear()
        _warm_list_cast(self._conn)
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
        return sql_base.get_all_nodes(self)

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
        return sql_base.get_all_edges(self)

    def get_nodes_by_type(self, node_type: NodeType) -> Sequence[IRNode]:
        return sql_base.get_nodes_by_type(self, node_type)

    def get_nodes_by_source(self, source: str) -> Sequence[IRNode]:
        return sql_base.get_nodes_by_source(self, source)

    def search_nodes_by_name(self, name_substring: str) -> Sequence[IRNode]:
        return sql_base.search_nodes_by_name(self, name_substring)

    def get_node_ids(self) -> set[str]:
        return sql_base.get_node_ids(self)

    def get_edge_keys(self) -> set[tuple[str, str, str]]:
        return sql_base.get_edge_keys(self)

    def node_count(self) -> int:
        return sql_base.node_count(self)

    def edge_count(self) -> int:
        return sql_base.edge_count(self)

    # Batch operations (Phase 2 hardened)
    def add_nodes(self, nodes: Sequence[IRNode]) -> None:
        if not nodes:
            return
        rows = [
            [n.id, n.type.name, n.name, n.source,
             n.confidence, json.dumps(n.metadata, default=str)]
            for n in nodes
        ]
        self._upsert_rows("graph_nodes", "id", rows)

    def add_edges(self, edges: Sequence[IREdge]) -> None:
        if not edges:
            return
        rows = [
            [e.from_node, e.to_node, e.type.name,
             e.weight, e.confidence, json.dumps(e.metadata, default=str)]
            for e in edges
        ]
        self._upsert_rows("graph_edges", ["from_node", "to_node", "type"], rows)

    def _upsert_rows(
        self,
        table: str,
        key_columns: str | list[str],
        rows: list[list[object]],
    ) -> None:
        # executemany with INSERT OR REPLACE rebuilds the PK index per row in DuckDB
        # and is orders of magnitude slower than a set-based unnest insert.
        keys = [key_columns] if isinstance(key_columns, str) else key_columns

        _warm_list_cast(self.conn)
        columns = self._table_columns(table)
        rows = _dedupe_by_key(rows, columns, keys)
        column_arrays = [[r[i] for r in rows] for i in range(len(columns))]
        unnest_select = ", ".join(f"unnest(?::VARCHAR[]) AS {col}" for col in columns)

        # The staging table mirrors whichever target is being written, so it is
        # keyed by table name — one per (connection, target) pair. Reusing a
        # single name would leave the node columns in place when edges are
        # written next, and the column count would not match.
        staging = f"_astra_batch_{table}"
        self.conn.execute(f"CREATE TEMP TABLE IF NOT EXISTS {staging} AS SELECT * FROM " + table + " LIMIT 0")
        self.conn.execute(f"DELETE FROM {staging}")
        self.conn.execute(
            f"INSERT INTO {staging} SELECT * FROM (SELECT {unnest_select} FROM (SELECT 1) _) AS batch",
            column_arrays,
        )
        self.conn.execute(
            f"DELETE FROM {table} WHERE EXISTS ("
            f"SELECT 1 FROM {staging} WHERE "
            + " AND ".join(f"{staging}.{k} = {table}.{k}" for k in keys)
            + ")"
        )
        self.conn.execute(f"INSERT INTO {table} SELECT * FROM {staging}")

    def _table_columns(self, table: str) -> list[str]:
        # The schema is fixed after connect(), so this is asked once per table
        # rather than once per batch.
        cached = self._column_cache.get(table)
        if cached is not None:
            return cached
        rows = self.conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ? ORDER BY ordinal_position",
            [table],
        ).fetchall()
        columns = [r[0] for r in rows]
        self._column_cache[table] = columns
        return columns

    def transaction(self):
        return _DuckDBTransaction(self)


class _DuckDBTransaction:
    """Atomic transaction context for DuckDB."""

    def __init__(self, backend: "DuckDBBackend") -> None:
        self._backend = backend
        self._committed = False

    def __enter__(self) -> "_DuckDBTransaction":
        self._backend.conn.execute("BEGIN TRANSACTION")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is None and not self._committed:
            self._backend.conn.execute("COMMIT")
            self._committed = True
        elif exc_type is not None:
            self._backend.conn.execute("ROLLBACK")

    def commit(self) -> None:
        if not self._committed:
            self._backend.conn.execute("COMMIT")
            self._committed = True

    def rollback(self) -> None:
        if not self._committed:
            self._backend.conn.execute("ROLLBACK")
            self._committed = True
