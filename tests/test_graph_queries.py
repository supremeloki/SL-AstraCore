import shutil
import tempfile
from pathlib import Path

from astra.graph.in_memory_storage import InMemoryGraphStorage
from astra.graph.query_engine import GraphQueryEngine
from astra.storage.backend import StorageProvider
from astra.ir.models import EdgeType, IREdge, IRNode, NodeType


def _chain_storage():
    storage = InMemoryGraphStorage()
    ids = ["file:a", "file:b", "file:c", "file:d"]
    for nid in ids:
        storage.add_node(IRNode(id=nid, type=NodeType.FILE, name=nid, source="parser"))
    storage.write_edges([
        IREdge(from_node="file:a", to_node="file:b", type=EdgeType.IMPORTS),
        IREdge(from_node="file:b", to_node="file:c", type=EdgeType.IMPORTS),
        IREdge(from_node="file:c", to_node="file:d", type=EdgeType.IMPORTS),
        IREdge(from_node="file:d", to_node="file:a", type=EdgeType.REFERENCES),
    ])
    return storage


def test_shortest_path_on_chain():
    engine = GraphQueryEngine(_chain_storage())
    path = engine.shortest_path("file:a", "file:c")
    assert path == ["file:a", "file:b", "file:c"]


def test_shortest_path_returns_none_when_unreachable():
    storage = InMemoryGraphStorage()
    storage.add_node(IRNode(id="file:x", type=NodeType.FILE, name="x", source="parser"))
    storage.add_node(IRNode(id="file:y", type=NodeType.FILE, name="y", source="parser"))
    path = GraphQueryEngine(storage).shortest_path("file:x", "file:y")
    assert path is None


def test_shortest_path_same_node():
    engine = GraphQueryEngine(_chain_storage())
    assert engine.shortest_path("file:a", "file:a") == ["file:a"]


def test_extract_subgraph_keeps_only_induced_edges():
    engine = GraphQueryEngine(_chain_storage())
    result = engine.extract_subgraph(["file:a", "file:b", "file:d"])
    node_ids = {n.id for n in result.nodes}
    assert node_ids == {"file:a", "file:b", "file:d"}
    edge_pairs = {(e.from_node, e.to_node) for e in result.edges}
    assert ("file:a", "file:b") in edge_pairs
    assert ("file:d", "file:a") in edge_pairs
    assert all(e.to_node != "file:c" and e.from_node != "file:c" for e in result.edges)


def test_impact_analysis_follows_dependents_and_is_depth_capped():
    """Impact means "who breaks if I change this", so it walks edges backwards.

    The chain is a->b, b->c, c->d, d->a. Editing file:a affects whoever
    imports it — file:d directly, and file:c through d. Walking forward would
    have reported b and c instead, which is the opposite of the question.
    """
    engine = GraphQueryEngine(_chain_storage())
    shallow = {n.id for n in engine.impact_analysis("file:a", depth=1).nodes}
    assert shallow == {"file:d"}
    deeper = {n.id for n in engine.impact_analysis("file:a", depth=2).nodes}
    assert deeper == {"file:d", "file:c"}
    full = {n.id for n in engine.impact_analysis("file:a", depth=10).nodes}
    assert full == {"file:d", "file:c", "file:b"}


def _index(tmp_root):
    from astra.runtime.orchestrator import RuntimeOrchestrator

    orch = RuntimeOrchestrator()
    orch.register_repo(str(tmp_root))
    return orch, orch.index_repo(str(tmp_root))


def test_enricher_wiring_populates_conflicts():
    """Naming conflicts are detected during indexing, on the live pipeline."""
    root = Path(tempfile.mkdtemp())
    try:
        for rel in ("pkg/mod_a.py", "other/mod_a.py"):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def run():\n    return 1\n", encoding="utf-8")
        (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")

        _orch, record = _index(root)
        storage = StorageProvider(backend="duckdb", db_path=record.db_path).create()
        storage.connect()
        try:
            conflicts = [n for n in storage.get_all_nodes() if n.type.name == "CONFLICT"]
            assert conflicts, "naming conflict between the two mod_a.py copies expected"
            assert all(n.id.startswith("conflict:") for n in conflicts)
            assert any("mod_a.py" in n.name for n in conflicts)
        finally:
            storage.close()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_enricher_wiring_populates_patterns():
    """Design-pattern and naming-convention detection run during indexing."""
    root = Path(tempfile.mkdtemp())
    try:
        (root / "src" / "repository").mkdir(parents=True)
        (root / "src" / "repository" / "user_repository.py").write_text(
            "class UserRepository:\n    pass\n", encoding="utf-8"
        )
        (root / "src" / "repository" / "order_repository.py").write_text(
            "class OrderRepository:\n    pass\n", encoding="utf-8"
        )

        _orch, record = _index(root)
        storage = StorageProvider(backend="duckdb", db_path=record.db_path).create()
        storage.connect()
        try:
            patterns = [n.name for n in storage.get_all_nodes() if n.type.name == "PATTERN"]
            assert "repository" in patterns
            assert any(p.startswith("naming:") for p in patterns)
        finally:
            storage.close()
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_indexed_symbols_reach_the_graph():
    """The indexer must persist parsed functions/classes, not just files."""
    root = Path(tempfile.mkdtemp())
    try:
        (root / "svc.py").write_text("class Service:\n    pass\n\ndef run():\n    return 1\n", encoding="utf-8")

        _orch, record = _index(root)
        storage = StorageProvider(backend="duckdb", db_path=record.db_path).create()
        storage.connect()
        try:
            names = {n.name for n in storage.get_all_nodes()}
            assert "Service" in names and "run" in names
        finally:
            storage.close()
    finally:
        shutil.rmtree(root, ignore_errors=True)
