import time

from astra.context.engine import ContextEngine
from astra.context.retrieval import ContextCache, ContextRetrievalEngine
from astra.graph.in_memory_storage import InMemoryGraphStorage
from astra.graph.mutator import GraphMutator
from astra.ir.models import IRNode, IREdge, NodeType, EdgeType


def _build_graph():
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)

    mutator.apply_node_upsert(
        IRNode(id="file:a.py", type=NodeType.FILE, name="a.py", source="parser")
    )
    mutator.apply_node_upsert(
        IRNode(id="file:b.py", type=NodeType.FILE, name="b.py", source="parser")
    )

    mutator.apply_edge_upsert(
        IREdge(from_node="file:a.py", to_node="file:b.py", type=EdgeType.IMPORTS)
    )

    return storage


def test_cache_key_deterministic():
    cache = ContextCache()

    k1 = cache.make_key("query", ["a", "b"], 1000)
    k2 = cache.make_key("query", ["b", "a"], 1000)

    assert k1 == k2


def test_cache_put_get():
    storage = _build_graph()
    engine = ContextEngine(storage)
    retrieval = ContextRetrievalEngine(engine)

    p1 = retrieval.retrieve("understand", ["file:a.py"])
    p2 = retrieval.retrieve("understand", ["file:a.py"])

    assert p1 == p2


def test_cache_expiration():
    cache = ContextCache(ttl_seconds=1)

    key = cache.make_key("x", ["a"], 100)
    storage = _build_graph()
    engine = ContextEngine(storage)
    pack = engine.generate_context_pack("x", ["file:a.py"])

    cache.put(key, pack)
    assert cache.get(key) is not None

    time.sleep(1.2)
    assert cache.get(key) is None


def test_cache_eviction():
    cache = ContextCache(max_entries=1)

    storage = _build_graph()
    engine = ContextEngine(storage)
    pack = engine.generate_context_pack("x", ["file:a.py"])

    cache.put("a", pack)
    cache.put("b", pack)

    stats = cache.stats()
    assert stats["entries"] == 1


def test_retrieval_without_cache():
    storage = _build_graph()
    engine = ContextEngine(storage)
    retrieval = ContextRetrievalEngine(engine)

    p1 = retrieval.retrieve("q", ["file:a.py"], use_cache=False)
    p2 = retrieval.retrieve("q", ["file:a.py"], use_cache=False)

    assert p1 == p2
