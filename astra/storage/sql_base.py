"""Shared row-mapping and query logic for the two SQL backends.

DuckDB and SQLite differ in three places: how a query returns rows, the DDL,
and the batch upsert. Everything else — turning rows into IRNode/IREdge,
LIKE escaping, counting, key sets — is identical and lives here, so the two
backends only implement what actually differs.

Subclasses provide: ``execute(sql, params)`` returning row tuples, plus the
DDL and upsert.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, Sequence

from astra.ir.models import IREdge, IRNode, NodeType, EdgeType


def node_from_row(row: Sequence[Any]) -> IRNode:
    return IRNode(
        id=row[0],
        type=NodeType[row[1]] if isinstance(row[1], str) else row[1],
        name=row[2],
        source=row[3],
        confidence=row[4],
        metadata=json.loads(row[5]) if row[5] else {},
    )


def edge_from_row(row: Sequence[Any]) -> IREdge:
    return IREdge(
        from_node=row[0],
        to_node=row[1],
        type=EdgeType[row[2]] if isinstance(row[2], str) else row[2],
        weight=row[3],
        confidence=row[4],
        metadata=json.loads(row[5]) if row[5] else {},
    )


def like_pattern(name_substring: str) -> str:
    """Escape LIKE wildcards so a search for "100%" is a literal search.

    Both backends need ESCAPE '\\\\' on the query too, which is the caller's
    job; this only produces the value.
    """
    escaped = name_substring.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class SqlBackendBase(Protocol):
    """What a backend must supply for the shared methods to work."""

    @property
    def conn(self) -> Any: ...


def _rows(backend: Any, sql: str, params: Sequence[Any] | None = None) -> list[Sequence[Any]]:
    cursor = backend.conn.execute(sql, params) if params is not None else backend.conn.execute(sql)
    fetched = cursor.fetchall()
    return fetched


# The functions below are mixed into each backend class, so a backend only
# writes what is genuinely different and inherits the other 20-odd methods.
# Each takes ``self`` as the backend instance.


def get_all_nodes(self: Any) -> list[IRNode]:
    return [node_from_row(r) for r in _rows(self, "SELECT * FROM graph_nodes")]


def get_all_edges(self: Any) -> list[IREdge]:
    return [edge_from_row(r) for r in _rows(self, "SELECT * FROM graph_edges")]


def get_node_ids(self: Any) -> set[str]:
    return {r[0] for r in _rows(self, "SELECT id FROM graph_nodes")}


def get_edge_keys(self: Any) -> set[tuple[str, str, str]]:
    return {
        (r[0], r[1], r[2])
        for r in _rows(self, "SELECT from_node, to_node, type FROM graph_edges")
    }


def node_count(self: Any) -> int:
    row = self.conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()
    return int(row[0]) if row else 0


def edge_count(self: Any) -> int:
    row = self.conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()
    return int(row[0]) if row else 0


def search_nodes_by_name(self: Any, name_substring: str) -> list[IRNode]:
    rows = _rows(
        self,
        "SELECT * FROM graph_nodes WHERE name LIKE ? ESCAPE '\\'",
        [like_pattern(name_substring)],
    )
    return [node_from_row(r) for r in rows]


def get_nodes_by_type(self: Any, node_type: NodeType) -> list[IRNode]:
    value = node_type.name if isinstance(node_type, NodeType) else str(node_type)
    rows = _rows(self, "SELECT * FROM graph_nodes WHERE type = ?", [value])
    return [node_from_row(r) for r in rows]


def get_nodes_by_source(self: Any, source: str) -> list[IRNode]:
    rows = _rows(self, "SELECT * FROM graph_nodes WHERE source = ?", [source])
    return [node_from_row(r) for r in rows]


if __name__ == "__main__":
    assert like_pattern("100%") == "%100\\%%"
    assert like_pattern("a_b") == "%a\\_b%"
    assert like_pattern("back\\slash") == "%back\\\\slash%"
    print("ok")
