from astra.agents.adapter import AgentAdapterLayer
from astra.agents.providers import CodexProvider, GenericProvider
from astra.context.engine import ContextEngine
from astra.graph.in_memory_storage import InMemoryGraphStorage
from astra.graph.mutator import GraphMutator
from astra.ir.models import IRNode, IREdge, NodeType, EdgeType


def _build_context():
    storage = InMemoryGraphStorage()
    mutator = GraphMutator(storage)
    mutator.apply_node_upsert(
        IRNode(id="file:main.py", type=NodeType.FILE, name="main.py", source="parser")
    )
    mutator.apply_node_upsert(
        IRNode(id="file:utils.py", type=NodeType.FILE, name="utils.py", source="parser")
    )
    mutator.apply_edge_upsert(
        IREdge(from_node="file:main.py", to_node="file:utils.py", type=EdgeType.IMPORTS)
    )
    engine = ContextEngine(storage)
    return engine.generate_context_pack("understand main", ["file:main.py"])


def test_adapter_build_request():
    ctx = _build_context()
    adapter = AgentAdapterLayer()
    request = adapter.build_request("analyze main", ctx)
    assert request.task_description == "analyze main"
    assert "nodes" in request.context_payload
    assert "edges" in request.context_payload
    assert len(request.context_payload["nodes"]) >= 1
    assert len(request.context_payload["edges"]) >= 1


def test_provider_resolution():
    adapter = AgentAdapterLayer(providers=[CodexProvider(), GenericProvider()])
    provider = adapter.resolve_provider("refactor the code")
    assert provider.name == "codex"
    provider2 = adapter.resolve_provider("write documentation")
    assert provider2.name == "generic"


def test_execute_with_response():
    ctx = _build_context()
    adapter = AgentAdapterLayer()
    response = adapter.execute("analyze", ctx, response_text="ok")
    assert response.content == "ok"
    assert response.confidence > 0.0


def test_execute_without_response():
    ctx = _build_context()
    adapter = AgentAdapterLayer()
    response = adapter.execute("analyze", ctx)
    assert response is not None
    assert response.provider


def test_provider_tools():
    codex = CodexProvider()
    assert codex.supports_tool("file_write")
    assert not codex.supports_tool("web_search")

    generic = GenericProvider()
    assert generic.supports_tool("file_read")
    assert not generic.supports_tool("code_execution")


def test_provider_registration():
    adapter = AgentAdapterLayer()
    initial_count = len(adapter._providers)
    adapter.register(CodexProvider())
    assert len(adapter._providers) == initial_count + 1
