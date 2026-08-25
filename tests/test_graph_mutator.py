from astra.graph.mutator import GraphMutator, compute_diff, compute_edge_diff, GraphMutationResult
from astra.graph.in_memory_storage import InMemoryGraphStorage
from astra.ir.models import IRNode, IREdge, NodeType, EdgeType


def test_node_upsert_adds_new():
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)

    node = IRNode(id="n1", type=NodeType.FILE, name="a", source="test")
    result = mutator.apply_node_upsert(node)

    assert result.added_nodes == 1
    assert result.updated_nodes == 0
    assert storage.get_node("n1") == node


def test_node_upsert_idempotent():
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)

    node = IRNode(id="n1", type=NodeType.FILE, name="a", source="test")
    mutator.apply_node_upsert(node)
    result = mutator.apply_node_upsert(node)

    assert result.added_nodes == 0
    assert result.updated_nodes == 0


def test_node_delete_cascades_edges():
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)

    n1 = IRNode(id="n1", type=NodeType.FILE, name="a", source="t")
    n2 = IRNode(id="n2", type=NodeType.FILE, name="b", source="t")
    mutator.apply_node_upsert(n1)
    mutator.apply_node_upsert(n2)

    mutator.apply_edge_upsert(IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS))

    result = mutator.apply_node_delete("n1")

    assert result.removed_nodes == 1
    assert result.removed_edges == 1


def test_node_delete_counts_self_loop_once():
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)

    mutator.apply_node_upsert(IRNode(id="n1", type=NodeType.FILE, name="a", source="t"))
    mutator.apply_node_upsert(IRNode(id="n2", type=NodeType.FILE, name="b", source="t"))
    mutator.apply_edge_upsert(IREdge(from_node="n1", to_node="n1", type=EdgeType.CALLS))
    mutator.apply_edge_upsert(IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS))

    result = mutator.apply_node_delete("n1")

    assert result.removed_nodes == 1
    assert result.removed_edges == 2
    assert storage.get_edges() == []


def test_edge_upsert_adds_new():
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)

    edge = IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS)
    result = mutator.apply_edge_upsert(edge)

    assert result.added_edges == 1
    assert result.updated_edges == 0


def test_edge_upsert_idempotent():
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)

    edge = IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS)
    mutator.apply_edge_upsert(edge)
    result = mutator.apply_edge_upsert(edge)

    assert result.added_edges == 0


def test_edge_delete():
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)

    edge = IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS)
    mutator.apply_edge_upsert(edge)

    result = mutator.apply_edge_delete("n1", "n2", EdgeType.IMPORTS)

    assert result.removed_edges == 1
    assert storage.get_edges() == []


def test_batch_mutation():
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)

    n1 = IRNode(id="n1", type=NodeType.FILE, name="a", source="t")
    n2 = IRNode(id="n2", type=NodeType.FILE, name="b", source="t")
    edge = IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS)

    result = mutator.apply_batch(
        nodes_to_upsert=[n1, n2],
        edges_to_upsert=[edge],
    )

    assert result.added_nodes == 2
    assert result.added_edges == 1


def test_compute_node_diff():
    n1_old = IRNode(id="n1", type=NodeType.FILE, name="a", source="t")
    n2_old = IRNode(id="n2", type=NodeType.FILE, name="b", source="t")
    n3_old = IRNode(id="n3", type=NodeType.FILE, name="c", source="t")

    old = {"n1": n1_old, "n2": n2_old, "n3": n3_old}

    n1_new = IRNode(id="n1", type=NodeType.FILE, name="a_changed", source="t")
    n4_new = IRNode(id="n4", type=NodeType.FILE, name="d", source="t")

    new = {"n1": n1_new, "n4": n4_new}

    upsert, delete = compute_diff(old, new)

    assert "n3" in delete
    assert "n2" in delete
    assert any(n.id == "n1" for n in upsert)
    assert any(n.id == "n4" for n in upsert)


def test_compute_edge_diff():
    e1_old = IREdge(from_node="a", to_node="b", type=EdgeType.IMPORTS)
    e2_old = IREdge(from_node="b", to_node="c", type=EdgeType.CALLS)
    e3_old = IREdge(from_node="c", to_node="d", type=EdgeType.REFERENCES)

    old_edges = [e1_old, e2_old]
    new_edges = [e1_old, e3_old]

    upsert, delete = compute_edge_diff(old_edges, new_edges)

    assert any(e.to_node == "d" for e in upsert)
    assert any(key[1] == "c" for key in delete)  # to_node is second element of key tuple