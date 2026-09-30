from astra.context.engine import ContextEngine
from astra.graph.in_memory_storage import InMemoryGraphStorage
from astra.ir.models import IRNode, IREdge, NodeType, EdgeType

def test_generate_context_pack():
    storage = InMemoryGraphStorage()
    engine = ContextEngine(storage)

    n1 = IRNode(id="n1", type=NodeType.FILE, name="a", source="t")
    n2 = IRNode(id="n2", type=NodeType.FILE, name="b", source="t")
    n3 = IRNode(id="n3", type=NodeType.FILE, name="c", source="t")

    storage.add_node(n1)
    storage.add_node(n2)
    storage.add_node(n3)

    # n1 -> n2 -> n3
    storage.add_edge(IREdge(from_node="n1", to_node="n2", type=EdgeType.IMPORTS))
    storage.add_edge(IREdge(from_node="n2", to_node="n3", type=EdgeType.IMPORTS))

    pack = engine.generate_context_pack(
        query_intent="test",
        seed_nodes=["n1"]
    )

    # Should capture n1, n2 (1-hop)
    assert len(pack.nodes) == 2
    assert any(n.node_id == "n1" for n in pack.nodes)
    assert any(n.node_id == "n2" for n in pack.nodes)
    assert not any(n.node_id == "n3" for n in pack.nodes)


def test_ranking_reaches_the_pack_instead_of_defaulting_to_one(tmp_path):
    """The selector used to drop the score, so every node reported 1.0 and the
    UI could not tell a strong match from padding."""
    import logging

    from astra.runtime.orchestrator import RuntimeOrchestrator

    logging.disable(logging.CRITICAL)
    for i in range(4):
        (tmp_path / f"mod{i}.py").write_text(
            f"def parser_helper_{i}():\n    return {i}\n", encoding="utf-8"
        )
    (tmp_path / "app.py").write_text(
        "from mod0 import parser_helper_0\n\ndef main():\n    return parser_helper_0()\n",
        encoding="utf-8",
    )

    orch = RuntimeOrchestrator()
    orch.register_repo(str(tmp_path))
    orch.index_repo(str(tmp_path))

    pack = orch.query_context(str(tmp_path), seed_node_ids=[], query_intent="parser", max_tokens=4000)
    scores = {n.relevance_score for n in pack.nodes}
    assert len(scores) > 1, "every node has the same score — ranking is not applied"
    assert max(scores) != 1.0, "score is still the 1.0 default"
