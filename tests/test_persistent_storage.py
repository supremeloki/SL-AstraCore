"""
2A — Persistent graph backend tests.

Verifies DuckDB and SQLite backends implement the StorageBackend protocol
with identical behavior: CRUD, cascade delete, search, stats, persistence.
"""
from __future__ import annotations

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


def _run_backend_tests(backend_name: str, db_path: str):
    provider = StorageProvider(backend=backend_name, db_path=db_path)
    storage = provider.create()
    storage.connect()

    nodes = _make_nodes()
    edges = _make_edges()

    # Add nodes
    for n in nodes:
        storage.add_node(n)
    assert storage.node_count() == 3

    # Retrieve
    retrieved = storage.get_node("n1")
    assert retrieved is not None
    assert retrieved.name == "main"

    # Add edges
    for e in edges:
        storage.add_edge(e)
    assert storage.edge_count() == 2

    # Query edges
    out_edges = storage.get_edges(from_node="n1")
    assert len(out_edges) == 2

    filtered = storage.get_edges(from_node="n1", edge_type=EdgeType.IMPORTS)
    assert len(filtered) == 1
    assert filtered[0].to_node == "n2"

    # Search nodes by name
    results = storage.search_nodes_by_name("utils")
    assert len(results) == 1
    assert results[0].id == "n2"

    # Filter by type
    class_nodes = storage.get_nodes_by_type(NodeType.CLASS)
    assert len(class_nodes) == 1
    assert class_nodes[0].name == "Greeter"

    # Node IDs
    ids = storage.get_node_ids()
    assert ids == {"n1", "n2", "n3"}

    # Edge keys
    keys = storage.get_edge_keys()
    assert ("n1", "n2", "IMPORTS") in keys

    # Delete edge
    storage.delete_edge("n1", "n2", EdgeType.IMPORTS)
    assert storage.edge_count() == 1

    # Cascade delete
    storage.delete_node("n1")
    assert storage.get_node("n1") is None
    remaining_edges = storage.get_all_edges()
    assert len(remaining_edges) == 0

    storage.close()


def test_duckdb_backend():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        db_path = f.name
    # Force delete existing file to ensure DuckDB creates it fresh
    if os.path.exists(db_path):
        os.remove(db_path)
    try:
        _run_backend_tests("duckdb", db_path)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_sqlite_backend():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    try:
        _run_backend_tests("sqlite", db_path)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_duckdb_persistence_across_sessions():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        db_path = f.name
    if os.path.exists(db_path):
        os.remove(db_path)
    try:
        # Session 1: write
        storage = StorageProvider(backend="duckdb", db_path=db_path).create()
        storage.connect()
        storage.add_node(IRNode(id="persist1", type=NodeType.FILE, name="test", source="t"))
        storage.close()

        # Session 2: read
        storage2 = StorageProvider(backend="duckdb", db_path=db_path).create()
        storage2.connect()
        node = storage2.get_node("persist1")
        assert node is not None
        assert node.name == "test"
        storage2.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_sqlite_persistence_across_sessions():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    try:
        storage = StorageProvider(backend="sqlite", db_path=db_path).create()
        storage.connect()
        storage.add_node(IRNode(id="persist2", type=NodeType.FILE, name="test", source="t"))
        storage.close()

        storage2 = StorageProvider(backend="sqlite", db_path=db_path).create()
        storage2.connect()
        node = storage2.get_node("persist2")
        assert node is not None
        assert node.name == "test"
        storage2.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_unknown_backend_raises():
    try:
        StorageProvider(backend="postgres", db_path="").create()
        assert False, "Should have raised"
    except ValueError:
        pass
