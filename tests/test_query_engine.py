from astra.graph.query_engine import GraphQueryEngine
from astra.storage.backend import StorageProvider
from astra.ir.models import IRNode, IREdge, NodeType, EdgeType
from astra.graph.mutator import GraphMutator

import os
import tempfile


def _build_test_graph():
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        db_path = f.name
    if os.path.exists(db_path):
        os.remove(db_path)

    storage = StorageProvider(backend="duckdb", db_path=db_path).create()
    storage.connect()
    mutator = GraphMutator(storage)

    n1 = IRNode(id="file:src/main.py", type=NodeType.FILE, name="main.py", source="parser",
                metadata={"language": "python"})
    n2 = IRNode(id="file:src/utils.py", type=NodeType.FILE, name="utils.py", source="parser",
                metadata={"language": "python"})
    n3 = IRNode(id="file:src/handlers.py", type=NodeType.FILE, name="handlers.py", source="parser",
                metadata={"language": "python"})

    mutator.apply_node_upsert(n1)
    mutator.apply_node_upsert(n2)
    mutator.apply_node_upsert(n3)

    mutator.apply_edge_upsert(IREdge(from_node="file:src/main.py", to_node="file:src/utils.py",
                                      type=EdgeType.IMPORTS))
    mutator.apply_edge_upsert(IREdge(from_node="file:src/main.py", to_node="file:src/handlers.py",
                                      type=EdgeType.IMPORTS))
    mutator.apply_edge_upsert(IREdge(from_node="file:src/handlers.py", to_node="file:src/utils.py",
                                      type=EdgeType.IMPORTS))

    return storage, db_path


def test_find_dependents():
    storage, db_path = _build_test_graph()
    try:
        engine = GraphQueryEngine(storage)

        result = engine.find_dependents("file:src/utils.py")
        assert result.count >= 2
        assert any(n.name == "main.py" for n in result.nodes)
        assert any(n.name == "handlers.py" for n in result.nodes)
    finally:
        storage.close()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_find_imports():
    storage, db_path = _build_test_graph()
    try:
        engine = GraphQueryEngine(storage)

        result = engine.find_imports("file:src/main.py")
        assert result.count == 2
        names = {n.name for n in result.nodes}
        assert "utils.py" in names
        assert "handlers.py" in names
    finally:
        storage.close()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_bfs_traversal():
    storage, db_path = _build_test_graph()
    try:
        engine = GraphQueryEngine(storage)

        result = engine.bfs("file:src/main.py", max_depth=1)
        names = {n.name for n in result.nodes}
        assert "main.py" in names
        assert "utils.py" in names
        assert "handlers.py" in names
    finally:
        storage.close()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_language_summary():
    storage, db_path = _build_test_graph()
    try:
        engine = GraphQueryEngine(storage)

        summary = engine.language_summary()
        assert summary.get("python", 0) == 3
    finally:
        storage.close()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_edge_type_summary():
    storage, db_path = _build_test_graph()
    try:
        engine = GraphQueryEngine(storage)

        summary = engine.edge_type_summary()
        assert summary.get("IMPORTS", 0) == 3
    finally:
        storage.close()
        if os.path.exists(db_path):
            os.remove(db_path)


def test_find_by_type():
    storage, db_path = _build_test_graph()
    try:
        engine = GraphQueryEngine(storage)

        result = engine.find_by_type(NodeType.FILE)
        assert result.count == 3
    finally:
        storage.close()
        if os.path.exists(db_path):
            os.remove(db_path)
