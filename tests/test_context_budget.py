"""Phase 4 — strict token budget enforcement.

Verifies:
  - engine.generate_context_pack respects max_tokens (seeds first)
  - total_tokens is the honest estimated sum, never clamped
  - task pack (ContextEngine.build_pack) never exceeds budget
  - file_path populated for file nodes
"""
from __future__ import annotations

from astra.context.engine import ContextEngine as SliceContextEngine
from astra.graph.in_memory_storage import InMemoryGraphStorage
from astra.ir.models import IRNode, IREdge, NodeType, EdgeType


def _build_graph():
    storage = InMemoryGraphStorage()
    for name in ["a", "b", "c", "d", "e"]:
        storage.add_node(IRNode(id=f"file:{name}.py", type=NodeType.FILE, name=f"{name}.py", source="t"))
    ids = [f"file:{n}.py" for n in ["a", "b", "c", "d", "e"]]
    for src, dst in zip(ids, ids[1:], strict=False):
        storage.add_edge(IREdge(from_node=src, to_node=dst, type=EdgeType.IMPORTS))
    return storage


def test_seeded_pack_respects_tiny_max_tokens():
    storage = _build_graph()
    engine = SliceContextEngine(storage)

    pack = engine.generate_context_pack("understand", ["file:a.py"], max_tokens=5)

    # Each node ref costs ~3-4 tokens ("file:a.py FILE a.py"); budget 5 => only the seed fits.
    assert len(pack.nodes) == 1
    assert pack.nodes[0].node_id == "file:a.py"
    assert 0 < pack.total_tokens <= 5


def test_total_tokens_is_honest_sum():
    storage = _build_graph()
    engine = SliceContextEngine(storage)

    pack = engine.generate_context_pack("understand", ["file:a.py"])

    from astra.context.token_budget import TokenBudget
    expected = sum(
        TokenBudget.estimate(f"{n.node_id} {n.node_type.name} {n.name}") for n in pack.nodes
    )
    assert pack.total_tokens == expected
    assert pack.total_tokens > 0


def test_budget_zero_admits_nothing():
    storage = _build_graph()
    engine = SliceContextEngine(storage)

    pack = engine.generate_context_pack("x", ["file:a.py"], max_tokens=0)

    assert pack.nodes == ()
    assert pack.token_budget == 0


def test_task_pack_never_exceeds_budget():
    from astra.models.graph_node import GraphNode, NodeType as GraphNodeType
    from astra.models.knowledge_graph import KnowledgeGraph
    from astra.context.context_engine import ContextEngine as TaskContextEngine

    kg = KnowledgeGraph()
    for i in range(40):
        nid = f"file:m{i:02d}.py"
        gn = GraphNode(
            id=nid,
            label=nid,
            node_type=GraphNodeType.FILE,
            confidence=0.9,
            properties={"file_path": f"src/m{i:02d}.py"},
        )
        kg.nodes.append(gn)
        kg.node_index[nid] = gn

    engine = TaskContextEngine(kg)
    engine._token_budget.set_budget(60)

    _analysis, pack, _deps, _risks = engine.build_pack("analyze module m01")

    assert pack.token_estimate <= 60


def test_file_path_populated_from_metadata():
    storage = InMemoryGraphStorage()
    storage.add_node(
        IRNode(
            id="file:src/main.py",
            type=NodeType.FILE,
            name="main.py",
            source="t",
            metadata={"file_path": "src/main.py"},
        )
    )
    engine = SliceContextEngine(storage)

    pack = engine.generate_context_pack("x", ["file:src/main.py"])

    assert len(pack.nodes) == 1
    assert pack.nodes[0].file_path == "src/main.py"


def test_file_path_populated_for_file_nodes():
    """Task pipeline path: file nodes carry file_path through to ContextNodeRef."""
    import tempfile
    from pathlib import Path

    from astra.parser.python_adapter import PythonParserAdapter
    from astra.parser.registry import ParserRegistry
    from astra.runtime.orchestrator import RuntimeOrchestrator

    tmpdir = tempfile.mkdtemp(prefix="astra_budget_")
    src = Path(tmpdir) / "src"
    src.mkdir()
    (src / "main.py").write_text("from src.helpers import go\n")
    (src / "helpers.py").write_text("def go():\n    return 1\n")

    registry = ParserRegistry()
    registry.register(PythonParserAdapter())
    runtime = RuntimeOrchestrator(parser_registry=registry)
    runtime.register_repo(tmpdir)
    runtime.index_repo(tmpdir)

    seed = f"file:{str((src / 'main.py').resolve())}"
    pack = runtime.query_context(root_path=tmpdir, seed_node_ids=[seed])

    file_refs = [n for n in pack.nodes if n.node_type == NodeType.FILE]
    assert file_refs
    assert all(n.file_path for n in file_refs)
