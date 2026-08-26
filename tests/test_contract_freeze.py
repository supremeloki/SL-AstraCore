"""2D — Contract Freeze Validation.

Ensures every api.py protocol matches its concrete implementation:
  - Each protocol method exists in the implementation class.
  - No drift between contract and code.
"""

from __future__ import annotations


from astra.storage.backend import StorageBackend
from astra.graph.api import GraphStorageAdapter
from astra.agents.adapter import AgentAdapter


def _protocol_methods(protocol) -> set[str]:
    return {
        name for name, value in vars(protocol).items()
        if callable(value) and not name.startswith("_")
    }


def test_storage_backend_contract():
    """DuckDB implements all StorageBackend methods."""
    from astra.storage.duckdb_backend import DuckDBBackend
    required = _protocol_methods(StorageBackend)
    actual = {m for m in dir(DuckDBBackend) if not m.startswith("_")}
    missing = required - actual
    assert not missing, f"DuckDBBackend missing protocol methods: {missing}"


def test_storage_backend_sqlite_contract():
    """SQLite implements all StorageBackend methods."""
    from astra.storage.sqlite_backend import SQLiteBackend
    required = _protocol_methods(StorageBackend)
    actual = {m for m in dir(SQLiteBackend) if not m.startswith("_")}
    missing = required - actual
    assert not missing, f"SQLiteBackend missing protocol methods: {missing}"


def test_agent_adapter_protocol():
    """AgentAdapterLayer implements AgentAdapter protocol."""
    from astra.agents.adapter import AgentAdapterLayer
    required = _protocol_methods(AgentAdapter)
    actual = {m for m in dir(AgentAdapterLayer) if not m.startswith("_")}
    missing = required - actual
    assert not missing, f"AgentAdapterLayer missing protocol methods: {missing}"


def test_graph_storage_adapter_contract():
    """InMemoryGraphStorage implements GraphStorageAdapter protocol."""
    from astra.graph.in_memory_storage import InMemoryGraphStorage
    required = _protocol_methods(GraphStorageAdapter)
    actual = {m for m in dir(InMemoryGraphStorage) if not m.startswith("_")}
    missing = required - actual
    assert not missing, f"InMemoryGraphStorage missing protocol methods: {missing}"


def test_iredge_field_contract():
    """IRNode/IREdge use canonical field names (id, type, name for nodes;
    from_node, to_node, type for edges)."""
    from astra.ir.models import IRNode, IREdge, NodeType, EdgeType
    n = IRNode(id="x", type=NodeType.FILE, name="test", source="t")
    assert hasattr(n, "id") and hasattr(n, "type") and hasattr(n, "name")
    e = IREdge(from_node="a", to_node="b", type=EdgeType.IMPORTS)
    assert hasattr(e, "from_node") and hasattr(e, "to_node") and hasattr(e, "type")
