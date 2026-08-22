from astra.graph.in_memory_storage import InMemoryGraphStorage
from astra.ir.models import IRNode, IREdge, NodeType, EdgeType


def test_add_and_get_node():
    storage = InMemoryGraphStorage()
    node = IRNode(id="n1", type=NodeType.FILE, name="test", source="test")
    storage.add_node(node)

    retrieved = storage.get_node("n1")
    assert retrieved == node


def test_add_and_get_edge():
    storage = InMemoryGraphStorage()
    edge = IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS)
    storage.add_edge(edge)

    edges = storage.get_edges(from_node="n1")
    assert len(edges) == 1
    assert edges[0] == edge


def test_delete_node_removes_related_edges():
    storage = InMemoryGraphStorage()

    n1 = IRNode(id="n1", type=NodeType.FILE, name="a", source="test")
    n2 = IRNode(id="n2", type=NodeType.FILE, name="b", source="test")
    edge = IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS)

    storage.add_node(n1)
    storage.add_node(n2)
    storage.add_edge(edge)

    storage.delete_node("n1")

    assert storage.get_node("n1") is None
    assert storage.get_edges() == []


def test_get_all_nodes_and_edges():
    storage = InMemoryGraphStorage()

    storage.add_node(IRNode(id="a", type=NodeType.FILE, name="a", source="x"))
    storage.add_node(IRNode(id="b", type=NodeType.FILE, name="b", source="x"))
    storage.add_edge(IREdge(from_node="a", to_node="b", type=EdgeType.IMPORTS))

    assert len(storage.get_all_nodes()) == 2
    assert len(storage.get_all_edges()) == 1
