"""2B+2C — Storage hardening + DuckDB/SQLite parity verification.

Verifies:
  - Batch add_nodes/add_edges on both backends
  - Transaction commit/rollback on both backends
  - Identical behavior across DuckDB and SQLite (parity)
"""

import os
import tempfile

from astra.ir.models import IRNode, IREdge, NodeType, EdgeType
from astra.storage.backend import StorageProvider


def _make_nodes():
    return [
        IRNode(id="n1", type=NodeType.FILE, name="main", source="parser"),
        IRNode(id="n2", type=NodeType.FILE, name="utils", source="parser"),
        IRNode(id="n3", type=NodeType.CLASS, name="Greeter", source="parser"),
    ]


def _make_edges():
    return [
        IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS),
        IREdge(from_node="n1", to_node="n3", type=EdgeType.REFERENCES),
    ]


def _run_batch_and_transaction_tests(backend_name: str, db_path: str):
    provider = StorageProvider(backend=backend_name, db_path=db_path)
    storage = provider.create()
    storage.connect()

    nodes = _make_nodes()
    edges = _make_edges()

    # Batch add nodes
    storage.add_nodes(nodes)
    assert storage.node_count() == 3

    # Batch add edges
    storage.add_edges(edges)
    assert storage.edge_count() == 2

    # Transaction commit
    with storage.transaction() as tx:
        storage.add_node(IRNode(id="n4", type=NodeType.FILE, name="extra", source="t"))
    assert storage.node_count() == 4

    # Transaction rollback
    try:
        with storage.transaction():
            storage.add_node(IRNode(id="n5", type=NodeType.FILE, name="temp", source="t"))
            raise ValueError("intentional rollback")
    except ValueError:
        pass
    assert storage.node_count() == 4  # n5 should NOT persist

    # Empty batch is noop
    storage.add_nodes([])
    storage.add_edges([])
    assert storage.node_count() == 4
    assert storage.edge_count() == 2

    storage.close()


def test_duckdb_batch_and_transaction():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        db_path = f.name
    if os.path.exists(db_path):
        os.remove(db_path)
    try:
        _run_batch_and_transaction_tests("duckdb", db_path)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_sqlite_batch_and_transaction():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    try:
        _run_batch_and_transaction_tests("sqlite", db_path)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# ── Parity: identical results across backends ──────────────────────


def _run_parity_assertions(backend_name: str, db_path: str):
    provider = StorageProvider(backend=backend_name, db_path=db_path)
    storage = provider.create()
    storage.connect()

    nodes = _make_nodes()
    edges = _make_edges()

    for n in nodes:
        storage.add_node(n)
    for e in edges:
        storage.add_edge(e)

    # Parity assertions
    assert storage.node_count() == 3
    assert storage.edge_count() == 2
    assert len(storage.get_all_nodes()) == 3
    assert len(storage.get_all_edges()) == 2
    assert storage.get_node("n1").name == "main"
    assert len(storage.get_edges(from_node="n1")) == 2
    assert len(storage.get_edges(from_node="n1", edge_type=EdgeType.IMPORTS)) == 1
    assert len(storage.search_nodes_by_name("utils")) == 1
    assert len(storage.get_nodes_by_type(NodeType.CLASS)) == 1
    assert storage.get_node_ids() == {"n1", "n2", "n3"}
    assert ("n1", "n2", "IMPORTS") in storage.get_edge_keys()

    storage.delete_edge("n1", "n2", EdgeType.IMPORTS)
    assert storage.edge_count() == 1

    storage.delete_node("n1")
    assert storage.get_node("n1") is None
    assert len(storage.get_all_edges()) == 0

    storage.close()


def test_duckdb_sqlite_parity():
    """Run identical operations on both backends and assert same results."""
    for backend, suffix in [("duckdb", ".duckdb"), ("sqlite", ".sqlite")]:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            db_path = f.name
        if backend == "duckdb" and os.path.exists(db_path):
            os.remove(db_path)
        try:
            _run_parity_assertions(backend, db_path)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


# ── Hardened behaviors ──────────────────────────────────────────────


def test_duckdb_duplicate_key_batch_upsert():
    provider = StorageProvider(backend="duckdb", db_path=":memory:")
    storage = provider.create()
    storage.connect()
    try:
        storage.add_nodes([
            IRNode(id="n1", type=NodeType.FILE, name="first", source="t"),
            IRNode(id="n1", type=NodeType.FILE, name="second", source="t"),
            IRNode(id="n2", type=NodeType.FILE, name="other", source="t"),
        ])
        assert storage.node_count() == 2
        assert storage.get_node("n1").name == "second"  # last occurrence wins

        storage.add_edges([
            IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS),
            IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS),
        ])
        assert storage.edge_count() == 1
    finally:
        storage.close()


def test_sqlite_metadata_roundtrip_reopen_equality():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    node = IRNode(
        id="n1", type=NodeType.CLASS, name="Greeter", source="t",
        metadata={"bases": ("object",), "nested": {"tags": ("a", "b")}},
    )
    edge = IREdge(from_node="n1", to_node="n1", type=EdgeType.CALLS,
                  metadata={"sites": ("line10",)})
    from astra.graph.mutator import GraphMutator

    try:
        first = StorageProvider(backend="sqlite", db_path=db_path).create()
        first.connect()
        first.add_node(node)
        first.add_edge(edge)
        first.close()

        second = StorageProvider(backend="sqlite", db_path=db_path).create()
        second.connect()
        assert second.get_node("n1") == node
        assert list(second.get_edges())[0] == edge

        result = GraphMutator(second).apply_node_upsert(node)
        assert result.added_nodes == 0
        assert result.updated_nodes == 0
        second.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_search_nodes_by_name_escapes_like_wildcards():
    for backend in ("duckdb", "sqlite"):
        provider = StorageProvider(backend=backend, db_path=":memory:")
        storage = provider.create()
        storage.connect()
        try:
            storage.add_nodes([
                IRNode(id="a", type=NodeType.FILE, name="100%_done", source="t"),
                IRNode(id="b", type=NodeType.FILE, name="100xdone", source="t"),
                IRNode(id="c", type=NodeType.FILE, name="plain", source="t"),
            ])
            hits = {n.id for n in storage.search_nodes_by_name("%")}
            assert hits == {"a"}
            hits = {n.id for n in storage.search_nodes_by_name("_")}
            assert hits == {"a"}
            assert len(storage.search_nodes_by_name("100%_done")) == 1
        finally:
            storage.close()
